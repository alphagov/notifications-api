![](https://travis-ci.org/alphagov/notifications-api.svg)
[![Requirements Status](https://requires.io/github/alphagov/notifications-api/requirements.svg?branch=master)](https://requires.io/github/alphagov/notifications-api/requirements/?branch=master)

# notifications-api
Notifications api
Application for the notification api.

Read and write notifications/status queue.
Get and update notification status.

mkvirtualenv -p /usr/local/bin/python3 notifications-api


```
export ADMIN_CLIENT_USER_NAME = 'dev-notify-admin'
export ADMIN_CLIENT_SECRET = 'dev-notify-secret-key'
export AWS_REGION='eu-west-1'
export DANGEROUS_SALT = 'dangerous-salt'
export DELIVERY_CLIENT_USER_NAME='dev-notify-delivery'
export DELIVERY_CLIENT_SECRET='dev-notify-secret-key'

export NOTIFY_JOB_QUEUE='notify-jobs-queue-[-unique-to-environment]'
export NOTIFICATION_QUEUE_PREFIX='notification_development[-unique-to-environment]'

export SECRET_KEY = 'secret-key'
export SQLALCHEMY_DATABASE_URI = 'postgresql://localhost/notification_api'
```