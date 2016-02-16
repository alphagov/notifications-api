![](https://travis-ci.org/alphagov/notifications-api.svg)
[![Requirements Status](https://requires.io/github/alphagov/notifications-api/requirements.svg?branch=master)](https://requires.io/github/alphagov/notifications-api/requirements/?branch=master)

# notifications-api
Notifications api
Application for the notification api.

Read and write notifications/status queue.
Get and update notification status.

## Setting up

```
mkvirtualenv -p /usr/local/bin/python3 notifications-api
echo "THINGS" > enviroment.sh
# * you’ll need to ask someone to know what the secret environment variables are
./scripts/bootstrap.sh
./scripts/run_app.sh
```
