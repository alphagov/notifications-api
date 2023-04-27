#!/bin/bash

# Define a common command prefix
WORKER_CMD="celery -A run_celery.notify_celery worker --pidfile=\"/tmp/celery.pid\" --loglevel=INFO --concurrency=4"
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

elif [ "$1" == "delivery-worker-retry-tasks" ]
then
  $COMMON_CMD retry-tasks 2> /dev/null

elif [ "$1" == "delivery-worker-letters" ]
then
  $COMMON_CMD create-letters-pdf-tasks,letter-tasks 2> /dev/null 
 
elif [ "$1" == "delivery-worker-jobs" ]
then
  $COMMON_CMD database-tasks,job-tasks 2> /dev/null 

elif [ "$1" == "delivery-worker-research" ]
then
  $COMMON_CMD research-mode-tasks 2> /dev/null 

elif [ "$1" == "delivery-worker-sender" ]
then
  celery multi start 3 -c 4 -A run_celery.notify_celery --loglevel=INFO \
    --logfile=/dev/null --pidfile=/tmp/celery%N.pid -Q send-sms-tasks,send-email-tasks

elif [ "$1" == "delivery-worker-sender-letters" ]
then
  $COMMON_CMD send-letter-tasks 2> /dev/null

elif [ "$1" == "delivery-worker-periodic" ]
then
  $COMMON_CMD periodic-tasks 2> /dev/null

elif [ "$1" == "delivery-worker-reporting" ]
then
  $COMMON_CMD reporting-tasks 2> /dev/null

elif [ "$1" == "delivery-worker-priority" ]
then
  $COMMON_CMD priority-tasks 2> /dev/null

# Only consume the notify-internal-tasks queue on this app so that Notify messages are processed as a priority
elif [ "$1" == "delivery-worker-internal" ]
then
  $COMMON_CMD notify-internal-tasks 2> /dev/null

elif [ "$1" == "delivery-worker-broadcasts" ]
then
  $COMMON_CMD broadcast-tasks 2> /dev/null

elif [ "$1" == "delivery-worker-receipts" ]
then
  $COMMON_CMD ses-callbacks,sms-callbacks 2> /dev/null

elif [ "$1" == "delivery-worker-service-callbacks" ]
then
  $COMMON_CMD service-callbacks,service-callbacks-retry 2> /dev/null

elif [ "$1" == "delivery-worker-save-api-notifications" ]
then
  $COMMON_CMD save-api-email-tasks,save-api-sms-tasks 2> /dev/null

elif [ "$1" == "delivery-celery-beat" ]
then
  celery -A run_celery.notify_celery beat --loglevel=INFO

else
  echo -e "'\033[31m'FATAL: missing argument'\033[0m'" && exit 1
  exit 1

fi
