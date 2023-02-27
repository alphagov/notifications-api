#!/bin/bash

if [ "$1" == "worker" ]
then
  shift 1
  # TODO: This is fine for local development but this file will soon need to change to have
  # many different celery workers like we currently do in production
  celery -A run_celery.notify_celery worker --pidfile="/tmp/celery.pid" --loglevel=INFO --concurrency=4
elif [ "$1" == "beat" ]
then
  shift 1
  celery -A run_celery.notify_celery beat --loglevel=INFO
elif [ "$1" == "migration" ]
then
  shift 1
  flask db upgrade
elif [ "$1" == "api" ]
then
  shift 1
  gunicorn -c /home/vcap/app/gunicorn_config.py application
elif [ -n "$*" ]
then
  $*
else
  echo -e "'\033[31m'FATAL: missing argument'\033[0m'" && exit 1
fi
