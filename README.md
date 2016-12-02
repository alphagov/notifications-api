[![Requirements Status](https://requires.io/github/alphagov/notifications-api/requirements.svg?branch=master)](https://requires.io/github/alphagov/notifications-api/requirements/?branch=master)

# notifications-api
Notifications api
Application for the notification api.

Read and write notifications/status queue.
Get and update notification status.

## Setting Up

### AWS credentials

To run the API you will need appropriate AWS credentials. You should receive these from whoever administrates your AWS account. Make sure you've got both an access key id and a secret access key.

Your aws credentials should be stored in a folder located at `~/.aws`. Follow [Amazon's instructions](http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html#cli-config-files) for storing them correctly.

### Virtualenv

```
mkvirtualenv -p /usr/local/bin/python3 notifications-api
```

### `environment.sh`

Creating the environment.sh file. Replace [unique-to-environment] with your something unique to the environment. Your AWS credentials should be set up for notify-tools (the development/CI AWS account).

Create a local environment.sh file containing the following:

```
echo "
export SQLALCHEMY_DATABASE_URI='postgresql://localhost/notification_api'
export SECRET_KEY='dev-notify-secret-key'
export DANGEROUS_SALT='dev-notify-salt'
export NOTIFY_ENVIRONMENT='development'
export ADMIN_CLIENT_SECRET='dev-notify-secret-key'
export ADMIN_BASE_URL='http://localhost:6012'
export FROM_NUMBER='development'
export MMG_URL='https://api.mmg.co.uk/json/api.php'
export MMG_API_KEY='MMG_API_KEY'
export LOADTESTING_API_KEY='FIRETEXT_SIMULATION_KEY'
export FIRETEXT_API_KEY='FIRETEXT_ACTUAL_KEY'
export STATSD_PREFIX='YOU_OWN_PREFIX'
export NOTIFICATION_QUEUE_PREFIX='YOUR_OWN_PREFIX'
export REDIS_URL="redis://localhost:6379/0"
"> environment.sh
```

NOTES:

 * Replace the placeholder key and prefix values as appropriate
 * The SECRET_KEY and DANGEROUS_SALT should match those in the [notifications-admin](https://github.com/alphagov/notifications-admin) app.
 * The  unique prefix for the queue names prevents clashing with others' queues in shared amazon environment and enables filtering by queue name in the SQS interface.

### Postgres

Install [Postgres.app](http://postgresapp.com/). You will need admin on your machine to do this.

### Redis

To switch redis on you'll need to install it locally. On a OSX we've used brew for this. To use redis caching you need to switch it on by changing the config for development:

        REDIS_ENABLED = True


##  To run the application

You need to run the api application and a local celery instance.

There are two run scripts for running all the necessary parts.

```
scripts/run_app.sh
```

```
scripts/run_celery.sh
```

```
scripts/run_celery_beat.sh
```


##  To test the application

First, ensure that `scripts/bootstrap.sh` has been run, as it creates the test database.

Then simply run

```
make test
```

That will run pep8 for code analysis and our unit test suite. If you wish to run our functional tests, instructions can be found in the
[notifications-functional-tests](https://github.com/alphagov/notifications-functional-tests) repository.



## To remove functional test data

NOTE: There is assumption that both the server name prefix and user name prefix are followed by a uuid.
The script will search for all services/users with that prefix and only remove it if the prefix is followed by a uuid otherwise it will be skipped.

Locally
```
python application.py purge_functional_test_data -u <functional tests user name prefix> # Remove the user and associated services.
```

On the server
```
python server_commands.py purge_functional_test_data -u <functional tests user name prefix> # Remove the user and associated services.
```
