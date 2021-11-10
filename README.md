# GOV.UK Notify API

Contains:
- the public-facing REST API for GOV.UK Notify, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation)
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/alphagov/notifications-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## Setting Up

### Python version

We run python 3.9 both locally and in production.

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

## To update application dependencies

`requirements.txt` is generated from the `requirements.in` in order to pin versions of all nested dependencies. If `requirements.in` has been changed, run `make freeze-requirements` to regenerate it.

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

## Further documentation

- [Writing public APIs](docs/writing-public-apis.md)
