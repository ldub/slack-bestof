<p align="center"><img width=12.5% src="https://user-images.githubusercontent.com/3114081/70684811-45182280-1c5c-11ea-8002-599735909b4e.png"></p>
<p align="center"><strong>slack-bestof</strong></p>
<p align="center"> find the most popular messages in your Slack workspace </p>

## Example

![image](https://user-images.githubusercontent.com/3114081/70684708-e81c6c80-1c5b-11ea-9aa4-ceb9537db779.png)

## Usage

### Overview
`slack-bestof` uses a Slack "legacy api token" to crawl the entire history of the configured slack channels and outputs some primitive statistics. It also uses a MongoDB instance to cache responses from the Slack API. Suggestions welcome!

### Set Up MongoDB

Due to rate-limiting, paging through the Slack API takes forever. We use a quick-n-dirty MongoDB in a docker container to cache slack messages locally for repeated runs.

```shell
docker pull mongo
docker run --name mongo_slack_bestof -d -p 127.0.0.1:27017:27017 mongo
```

### Get Slack API Token
Open the [Legacy Tokens](https://api.slack.com/custom-integrations/legacy-tokens) page in the Slack API docs. Scroll down and get yourself a token, they look like `xoxp-34232...`

### Make virtualenv (optional)
Virtualenv prevents this python package from polluting your system path.

```shell
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```


### Configure channels
`slack-bestof` needs a JSON file formatted like:
```
{
    "CAJSHDKAS": "example-channel-1",
    "CSDLHFSDD": "example-channel-2"
}
``` 

You can generate such a file with the following abomination:
```
echo "{" > channels.json
curl -s https://slack.com/api/channels.list?token=xoxp-your-token  | jq '.channels[] | "\"\(.id)\": \"\(.name)\","' -r | tee -a channels.json
sed '$ s/.$//' channels.json | tee channels.json
echo "}" >> channels.json
```

Note that you probably do not want to run `slack-bestof` on super noisy channels as it will take too long.

### Run `slack-bestof`

`slack-bestof` is configured to respect Slacks API rate limit (which they do enforce), so the first run will be slow but subsequent runs will use the data cached in mongodb.

```shell
export SLACK_API_TOKEN=<redacted>
export MONGODB_URI=mongodb://localhost:27017
source venv/bin/activate
pip install -e .
slack-bestof -t $SLACK_API_TOKEN -m $MONGODB_URI -c channels.json
```

### Clean up Docker image
Do this when you want to stop and remove the docker image and mongo database.

```shell
container_id=$(docker inspect mongo_slack_bestof --format='{{json .Id}}' | xargs)
docker stop $container_id
docker rm $container_id
```

### Limitations / TODO
It only ever queries for a single message once, so if people edit/add their reactions `slack-bestof` will not catch them. The best workaround is to either delete recent messages from MongoDB or delete the entire collection/database and re-sync from scratch.
