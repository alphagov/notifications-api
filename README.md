![](https://travis-ci.org/alphagov/notifications-api.svg)
[![Requirements Status](https://requires.io/github/alphagov/notifications-api/requirements.svg?branch=master)](https://requires.io/github/alphagov/notifications-api/requirements/?branch=master)

# notifications-api
Notifications api
Application for the notification api.

Read and write notifications/status queue.
Get and update notification status.

## Setting Up

```
mkvirtualenv -p /usr/local/bin/python3 notifications-api
```

Creating the environment.sh file. Replace [unique-to-environment] with your something unique to the environment. The local development environments are using the AWS on preview.

```
echo "
export ADMIN_CLIENT_USER_NAME = 'dev-notify-admin'
export ADMIN_CLIENT_SECRET = 'dev-notify-secret-key'
export AWS_REGION='eu-west-1'
export DANGEROUS_SALT = 'dangerous-salt'
export DELIVERY_CLIENT_USER_NAME='dev-notify-delivery'
export DELIVERY_CLIENT_SECRET='dev-notify-secret-key'
export NOTIFY_JOB_QUEUE='[unique-to-environment]-notify-jobs-queue'
export NOTIFICATION_QUEUE_PREFIX='[unique-to-environment]-notification_development'
export SECRET_KEY = 'secret-key'
export SQLALCHEMY_DATABASE_URI = 'postgresql://localhost/notification_api'
export VERIFY_CODE_FROM_EMAIL_ADDRESS='no-reply@notify.works' 
"> environment.sh
```

NOTE: the DELIVERY_CLIENT_USER_NAME, DELIVERY_CLIENT_SECRET, NOTIFY_JOB_QUEUE and NOTIFICATION_QUEUE_PREFIX must be the same as the ones in the [notifications-delivery](https://github.com/alphagov/notifications-delivery) app.
The SECRET_KEY and DANGEROUS_SALT are the same in [notifications-delivery](https://github.com/alphagov/notifications-delivery) and [notifications-admin](https://github.com/alphagov/notifications-admin) app