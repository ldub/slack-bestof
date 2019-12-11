from pymongo import ASCENDING, DESCENDING


def get_user_start_map(db, channels):
    """
    :param db: PyMongo DB
    :param channels: list of slack channel ids
    :return: map of (Slack User Id => User Join Timestamp)
    """
    all_users = db.messages.distinct("user")
    return {u: float(user_first_message(db, u, channels)['ts']) for u in all_users}


def user_first_message(db, user, channels):
    """
    :param db: PyMongo DB
    :param user: Slack User Id
    :param channels: list of Slack channel ids
    :return: First message ever sent by the user in one of the given channels
    """
    result_list = list(db.messages.find({"user": user, 'channel_id': {'$in': channels}}).sort("ts", 1).limit(1))
    return result_list[0] if len(result_list) else None


def users_started_by(start_map, timestamp):
    """
    :param start_map: map of (Slack User Id => User Join Timestamp)
    :param timestamp: any given time
    :return: al users that started before by the timestamp
    """
    return [u for u, ts in start_map.items() if ts <= timestamp]


def ensure_mongo_indexes(db):
    """
    Ensures that the messages collection in the given PyMongo db contains
    channel_id_1_ts_-1 and ts_1 indexes.
    """
    index_information = db.messages.index_information()
    if 'channel_id_1_ts_-1' not in index_information:
        db.messages.create_index([("channel_id", ASCENDING), ("ts", DESCENDING)], unique=True)

    if 'ts_1' not in index_information:
        db.messages.create_index([("ts", ASCENDING)])
