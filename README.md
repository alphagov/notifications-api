# GOV.UK Notify API

Contains:

- the public-facing REST API for GOV.UK Notify, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation)
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/alphagov/notifications-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## Setting Up

### Python version

At the moment we run Python 3.6 in production. You will run into problems if you try to use Python 3.5 or older, or Python 3.7 or newer.

### AWS credentials

To run the API you will need appropriate AWS credentials. See the [Wiki](https://github.com/alphagov/notifications-manuals/wiki/aws-accounts#how-to-set-up-local-development) for more details.

### `environment.sh`

Creating and edit an environment.sh file.

```
echo "
export NOTIFY_ENVIRONMENT='development'

export MMG_API_KEY='MMG_API_KEY'
export FIRETEXT_API_KEY='FIRETEXT_ACTUAL_KEY'
export NOTIFICATION_QUEUE_PREFIX='YOUR_OWN_PREFIX'

export FLASK_APP=application.py
export FLASK_ENV=development
export WERKZEUG_DEBUG_PIN=off
"> environment.sh
```

Things to change:

* Replace `YOUR_OWN_PREFIX` with `local_dev_<first name>`.
* Run the following in the credentials repo to get the API keys.

```
notify-pass credentials/providers/api_keys
```

### Postgres

Install [Postgres.app](http://postgresapp.com/).

Currently the API works with PostgreSQL 11. After installation, open the Postgres app, open the sidebar, and update or replace the default server with a compatible version.

**Note:** you may need to add the following directory to your PATH in order to bootstrap the app.

```
export PATH=${PATH}:/Applications/Postgres.app/Contents/Versions/11/bin/
```

### Redis

To switch redis on you'll need to install it locally. On a OSX we've used brew for this. To use redis caching you need to switch it on by changing the config for development:

        REDIS_ENABLED = True


##  To run the application

```
# install dependencies, etc.
make bootstrap

# run the web app
make run-flask

# run the background tasks
make run-celery

# run scheduled tasks (optional)
make run-celery-beat
```

##  To test the application

```
# install dependencies, etc.
make bootstrap

make test
```

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
1. Create new entries for your app in `manifest.yml.j2` and `scripts/paas_app_wrapper.sh` ([example](https://github.com/alphagov/notifications-api/pull/2486/commits/6163ca8b45813ff59b3a879f9cfcb28e55863e16))
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
