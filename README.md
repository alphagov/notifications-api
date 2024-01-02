# GOV.UK Notify API

Contains:
- the public-facing REST API for GOV.UK Notify, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation)
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/alphagov/notifications-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## Setting Up

### Python version

We run python 3.9 both locally and in production.

### psycopg2

[Follow these instructions on Mac M1 machines](https://github.com/psycopg/psycopg2/issues/1216#issuecomment-1068150544).

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
export FLASK_DEBUG=1
export WERKZEUG_DEBUG_PIN=off
"> environment.sh
```

Things to change:

* Replace `YOUR_OWN_PREFIX` with `local_dev_<first name>`.
* Run the following in the credentials repo to get the API keys.

```
notify-pass credentials/firetext
notify-pass credentials/mmg
```

### Postgres

Postgres is built in the CONCOURSE_TESTS as an extra layer derived from the TEST layer.
This is built to allow the tests to run using the API PRODUCTION layer.

#### How to build and run tests locally:

```
1. run the make command
    `make run-local-tests-with-docker`
```
The step above will build the image, run the container, start postgresql and run the tests.

Note: There is a file called "version.py.dist" that is used for "healthcheck.py". As it stands, this file is unusable and the local build will fail. You must, either rename it to "version.py" or simply create a local file with that name and copy the contents to it.


### Redis

To switch redis on you'll need to install it locally. On a Mac you can do:

```
# assuming you use Homebrew
brew install redis
brew services start redis
```

To use redis caching you need to switch it on with an environment variable:

```
export REDIS_ENABLED=1
```

### Pre-commit

We use [pre-commit](https://pre-commit.com/) to ensure that committed code meets basic standards for formatting, and will make basic fixes for you to save time and aggravation.

Install pre-commit system-wide with, eg `brew install pre-commit`. Then, install the hooks in this repository with `pre-commit install --install-hooks`.

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

We've had problems running Celery locally due to one of its dependencies: pycurl. Due to the complexity of the issue, we also support running Celery via Docker:

```
# install dependencies, etc.
make bootstrap-with-docker

# run the background tasks
make run-celery-with-docker

# run scheduled tasks
make run-celery-beat-with-docker
```

##  To test the application

```
# install dependencies, etc.
make bootstrap

make test
```

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
- [Updating dependencies](https://github.com/alphagov/notifications-manuals/wiki/Dependencies)
