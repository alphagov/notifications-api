[![Requirements Status](https://requires.io/github/alphagov/notifications-api/requirements.svg?branch=master)](https://requires.io/github/alphagov/notifications-api/requirements/?branch=master)
[![Coverage Status](https://coveralls.io/repos/alphagov/notifications-api/badge.svg?branch=master&service=github)](https://coveralls.io/github/alphagov/notifications-api?branch=master)

# GOV.UK Notify API

Contains:
- the public-facing REST API for GOV.UK Notify, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation)
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/alphagov/notifications-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## Setting Up

### AWS credentials

To run the API you will need appropriate AWS credentials. You should receive these from whoever administrates your AWS account. Make sure you've got both an access key id and a secret access key.

Your aws credentials should be stored in a folder located at `~/.aws`. Follow [Amazon's instructions](http://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html#cli-config-files) for storing them correctly.

### Virtualenv

```
mkvirtualenv -p /usr/local/bin/python3 notifications-api
```

### `environment.sh`

Creating the environment.sh file. Replace [unique-to-environment] with your something unique to the environment. Your AWS credentials should be set up for notify-tools (the development/CI AWS account).

Create a local environment.sh file containing the following:

```
echo "
export NOTIFY_ENVIRONMENT='development'

export MMG_API_KEY='MMG_API_KEY'
export LOADTESTING_API_KEY='FIRETEXT_SIMULATION_KEY'
export FIRETEXT_API_KEY='FIRETEXT_ACTUAL_KEY'
export NOTIFICATION_QUEUE_PREFIX='YOUR_OWN_PREFIX'

export FLASK_APP=application.py
export FLASK_DEBUG=1
export WERKZEUG_DEBUG_PIN=off
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

First, run `scripts/bootstrap.sh` to install dependencies and create the databases.

You need to run the api application and a local celery instance.

There are two run scripts for running all the necessary parts.

```
scripts/run_app.sh
```

```
scripts/run_celery.sh
```

Optionally you can also run this script to run the scheduled tasks:

```
scripts/run_celery_beat.sh
```


##  To test the application

First, ensure that `scripts/bootstrap.sh` has been run, as it creates the test database.

Then simply run

```
make test
```

That will run flake8 for code analysis and our unit test suite. If you wish to run our functional tests, instructions can be found in the
[notifications-functional-tests](https://github.com/alphagov/notifications-functional-tests) repository.


## To update application dependencies

`requirements.txt` file is generated from the `requirements-app.txt` in order to pin
versions of all nested dependencies. If `requirements-app.txt` has been changed (or
we want to update the unpinned nested dependencies) `requirements.txt` should be
regenerated with

```
make freeze-requirements
```

`requirements.txt` should be committed alongside `requirements-app.txt` changes.


## To run one off tasks

Tasks are run through the `flask` command - run `flask --help` for more information. There are two sections we need to
care about: `flask db` contains alembic migration commands, and `flask command` contains all of our custom commands. For
example, to purge all dynamically generated functional test data, do the following:

Locally
```
flask command purge_functional_test_data -u <functional tests user name prefix>
```

On the server
```
cf run-task notify-api "flask command purge_functional_test_data -u <functional tests user name prefix>"
```

All commands and command options have a --help command if you need more information.


## To create a new worker app

You need to:

1. Create a new entry for your app in manifest-delivery-base.yml ([example](https://github.com/alphagov/notifications-api/commit/131495125e5dfb181010c8595b11b34ab412fc37#diff-a1885d77ffd0a5cb168590428871cd9e))
1. Update the jenkins deployment job in the notifications-aws repo ([example](https://github.com/alphagov/notifications-aws/commit/69cf9912bd638bce088d4845e4b0a3b11a2cb74c#diff-17e034fe6186f2717b77ba277e0a5828))
1. Add the new worker's log group to the list of logs groups we get alerts about and we ship them to kibana ([example](https://github.com/alphagov/notifications-aws/commit/69cf9912bd638bce088d4845e4b0a3b11a2cb74c#diff-501ffa3502adce988e810875af546b97))
1. Optionally add it to the autoscaler ([example](https://github.com/alphagov/notifications-paas-autoscaler/commit/16d4cd0bdc851da2fab9fad1c9130eb94acf3d15))

**Important:**

Before pushing the deployment change on jenkins, read below about the first time deployment.

### First time deployment of your new worker

Our deployment flow requires that the app is present in order to proceed with the deployment.

This means that the first deployment of your app must happen manually.

To do this:

1. Ensure your code is backwards compatible
1. From the root of this repo run `CF_APP=<APP_NAME> make <cf-space> cf-push`

Once this is done, you can push your deployment changes to jenkins to have your app deployed on every deployment.
