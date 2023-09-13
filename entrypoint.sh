#!/bin/bash

#Cater for specific concurrency level
if [ "$1" == "api-worker-periodic" ] || [ "$1" == "api-worker-broadcasts" ]
then
  CONCURRENCY=2
elif [ "$1" == "api-worker-sender-letters" ]
  CONCURRENCY=3
else
  CONCURRENCY=4
fi

# Define a common command prefix
WORKER_CMD="celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=$CONCURRENCY"
COMMON_CMD="$WORKER_CMD -Q"

if [ "$1" == "worker" ]
then
  $WORKER_CMD

elif [ "$1" == "api" ]
then
  gunicorn -c /home/vcap/app/gunicorn_config.py application

elif [ "$1" == "api-local" ]
then
  flask run --host 0.0.0.0 --port $PORT

elif [ "$1" == "migration" ]
then
  flask db upgrade

elif [ "$1" == "api-worker-retry-tasks" ]
then
  $COMMON_CMD retry-tasks

elif [ "$1" == "api-worker-letters" ]
then
  $COMMON_CMD create-letters-pdf-tasks,letter-tasks

elif [ "$1" == "api-worker-jobs" ]
then
  $COMMON_CMD database-tasks,job-tasks

elif [ "$1" == "api-worker-research" ]
then
  $COMMON_CMD research-mode-tasks

elif [ "$1" == "api-worker-sender" ]
then
  $COMMON_CMD send-sms-tasks,send-email-tasks

elif [ "$1" == "api-worker-sender-letters" ]
then
  $COMMON_CMD send-letter-tasks

elif [ "$1" == "api-worker-periodic" ]
then
  $COMMON_CMD periodic-tasks

elif [ "$1" == "api-worker-reporting" ]
then
  $COMMON_CMD reporting-tasks

# Only consume the notify-internal-tasks queue on this app so that Notify messages are processed as a priority
elif [ "$1" == "api-worker-internal" ]
then
  $COMMON_CMD notify-internal-tasks

elif [ "$1" == "api-worker-broadcasts" ]
then
  $COMMON_CMD broadcast-tasks

elif [ "$1" == "api-worker-receipts" ]
then
  $COMMON_CMD ses-callbacks,sms-callbacks

elif [ "$1" == "api-worker-service-callbacks" ]
then
  $COMMON_CMD service-callbacks,service-callbacks-retry

elif [ "$1" == "api-worker-save-api-notifications" ]
then
  $COMMON_CMD save-api-email-tasks,save-api-sms-tasks

elif [ "$1" == "celery-beat" ]
then
  celery -A run_celery.notify_celery beat --loglevel=INFO

else
  echo -e "'\033[31m'FATAL: missing argument'\033[0m'" && exit 1
  exit 1

fi
