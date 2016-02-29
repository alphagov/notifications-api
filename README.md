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

Create a local environment.sh file containing the following:

```
echo "
export NOTIFY_API_ENVIRONMENT='config.Development'
export ADMIN_BASE_URL='http://localhost:6012'
export ADMIN_CLIENT_SECRET='dev-notify-secret-key'
export ADMIN_CLIENT_USER_NAME='dev-notify-admin'
export AWS_REGION='eu-west-1'
export DANGEROUS_SALT='dev-notify-salt'
export DELIVERY_CLIENT_USER_NAME='dev-notify-delivery'
export DELIVERY_CLIENT_SECRET='dev-notify-secret-key'
export FIRETEXT_API_KEY=[contact team member for api key] 
export FIRETEXT_NUMBER="Firetext"
export INVITATION_EXPIRATION_DAYS=2
export NOTIFY_EMAIL_DOMAIN='dev.notify.com'
export NOTIFY_JOB_QUEUE='[unique-to-environment]-notify-jobs-queue' # NOTE unique prefix
export NOTIFICATION_QUEUE_PREFIX='[unique-to-environment]-notification_development' # NOTE unique prefix
export SECRET_KEY='dev-notify-secret-key'
export SQLALCHEMY_DATABASE_URI = 'postgresql://localhost/notification_api'
export TWILIO_ACCOUNT_SID=[contact team member for account sid]
export TWILIO_AUTH_TOKEN=[contact team member for auth token]
export VERIFY_CODE_FROM_EMAIL_ADDRESS='no-reply@notify.works'
"> environment.sh
```

NOTE: the DELIVERY_CLIENT_USER_NAME, DELIVERY_CLIENT_SECRET, NOTIFY_JOB_QUEUE and NOTIFICATION_QUEUE_PREFIX must be the same as the ones in the [notifications-delivery](https://github.com/alphagov/notifications-delivery) app.
The SECRET_KEY and DANGEROUS_SALT are the same in [notifications-delivery](https://github.com/alphagov/notifications-delivery) and [notifications-admin](https://github.com/alphagov/notifications-admin) app.

NOTE:  Also note the  unique prefix for the queue names. This prevents clashing with others queues in shared amazon environment and using a prefix enables filtering by queue name in the SQS interface.



##  To run the application

You need to run the api application and a local celery instance.

There are two run scripts for running all the necessary parts.

```
scripts/run_app.sh
```

```
scripts/run_celery.sh
```

