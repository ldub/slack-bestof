import argparse
import functools
import heapq
import json
import logging
import time
from typing import Dict

from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import slack
from slack.errors import SlackApiError

from slack_bestof.util import get_user_start_map, users_started_by, ensure_mongo_indexes

logger = logging.getLogger("slack-bestof")
logging.basicConfig(format="%(asctime)s %(name)-13.13s [%(levelname)-5.5s]: %(message)s")
logger.setLevel(logging.DEBUG)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--slack-api-token", required=True)
    parser.add_argument("-m", "--mongodb-uri", required=True)
    parser.add_argument("-s", "--skip-slack-sync", action="store_true")
    parser.add_argument("-c", "--slack-channels-file", required=True)
    parser.add_argument("-l", "--leaderboard-size", default=10)
    args = parser.parse_args()

    SKIP_SLACK_SYNC = args.skip_slack_sync
    SLACK_CHANNELS_FILE = args.slack_channels_file
    LEADERBOARD_SIZE = args.leaderboard_size

    slack_channels: Dict[str, str]
    with open(SLACK_CHANNELS_FILE) as f:
        slack_channels = json.load(f)

    slack_client = slack.WebClient(token=args.slack_api_token)
    mongo_client = MongoClient(args.mongodb_uri)
    db = mongo_client.slack_bestof

    logger.info("Ensuring indexes...")
    ensure_mongo_indexes(db)

    throttled = False
    last_throttle_time = 0
    if not SKIP_SLACK_SYNC:
        for (channel_id, channel_name) in slack_channels.items():
            latest_message = list(db.messages.find({'channel_id': channel_id}).sort("ts", -1).limit(1))
            latest_message_ts = latest_message[0]['ts'] if len(latest_message) else 0
            logger.info("Syncing channel {} from {}".format(channel_name, latest_message_ts))

            channels_history_kwargs = {'channel': channel_id, 'oldest': latest_message_ts}
            while True:
                # https://api.slack.com/methods/channels.history is a "Tier 3" API, meaning that it gets throttled
                # above 50 calls/minute. 60 sec/50 = 1.2 sec sleep between pages.
                if throttled:
                    time.sleep(1.2)

                    # hackhackhack Slack lets us go over the limits sometimes, so unthrottle ourselves
                    if time.time() - last_throttle_time > 5 * 60:
                        throttled = False
                        logger.info("Unthrottling")
                try:
                    hist = slack_client.channels_history(**channels_history_kwargs)
                except SlackApiError as e:
                    logger.info("Slack throttled us.")
                    throttled = True
                    last_throttle_time = time.time()
                    continue

                for m in hist.data['messages']:
                    # Slack API doesn't return this data so we add it
                    m['channel_id'] = channel_id
                    m['channel_name'] = channel_name
                    try:
                        db.messages.insert_one(m)
                    except DuplicateKeyError:
                        # (channel_id, ts) is always unique in slack so we can ignore DuplicateKeyErrors
                        #   as they simply mean that we already synced this message
                        pass

                if hist['has_more']:
                    channels_history_kwargs['latest'] = hist['messages'][-1]['ts']
                else:
                    break

        logger.info("Done syncing")

    slack_channel_ids = list(slack_channels.keys())
    user_start_map = get_user_start_map(db, slack_channel_ids)
    slack_team_name = slack_client.team_info()['team']['domain']

    # Science the data! Much of the stuff we are doing in Python can be re-written in MongoDB query syntax.
    messages_with_reactions = \
        db.messages.find({'channel_id': {'$in': slack_channel_ids}, 'reactions': {'$exists': True, '$ne': []}})

    absolute_leaderboard = []
    normalized_leaderboard = []
    reacts = {}
    for message in messages_with_reactions:
        unique_reaction_users = set(functools.reduce(lambda users, x: [*users, *x['users']], message['reactions'], []))
        popularity_score = 100 * len(unique_reaction_users) / len(users_started_by(user_start_map, float(message['ts'])))
        message_link = f"https://{slack_team_name}.slack.com/archives/" \
                       f"{message['channel_id']}/p{message['ts'].replace('.', '')}"
        # convert minheap into maxheap by negating the popularity score
        # probably want a custom implementation that allows a maximum size if you have a large slack channel
        heapq.heappush(normalized_leaderboard, (-1 * popularity_score, message_link))
        heapq.heappush(absolute_leaderboard, (-1 * len(unique_reaction_users), message_link))
        # track reacts separately
        reaction_counts = {r['name']: r['count'] for r in message['reactions']}
        for name, count in reaction_counts.items():
            reacts[name] = reacts.get(name, 0) + count

    print()
    print()
    print("Most-Reacted Messages Leaderboard:")
    absolute_leaderboard = heapq.nsmallest(LEADERBOARD_SIZE, absolute_leaderboard)
    place = 1
    for neg_score, link in absolute_leaderboard:
        reacts_count = '%.2f' % (-1 * neg_score)  # un-negate from min-heap
        print(f"{place:02}. ({reacts_count} reacts): {link}")
        place = place + 1

    print()
    print()
    print("(Normalized) Most-Reacted Messages Leaderboard:")
    normalized_leaderboard = heapq.nsmallest(LEADERBOARD_SIZE, normalized_leaderboard)
    place = 1
    for neg_score, link in normalized_leaderboard:
        popularity_score = '%.2f' % (-1 * neg_score)  # un-negate from min-heap
        print(f"{place:02}. ({popularity_score}% reacted): {link}")
        place = place + 1

    print()
    print()
    print("Most-Used Reactions Leaderboard:")
    sorted_reacts = {k: v for k, v in sorted(reacts.items(), key=lambda item: item[1], reverse=True)}
    reacts_leaderboard = list(sorted_reacts.items())[:LEADERBOARD_SIZE]
    place = 1
    for name, count in reacts_leaderboard:
        print(f"{place:02}. ({count} times): :{name}:")
        place = place + 1
