#!/bin/bash

if [ -e "/etc/init/notifications-api.conf" ]
then
  echo "Starting api"
  sudo service notifications-api start
fi

if [ -e "/etc/init/notifications-api-celery-worker.conf" ]
then
  echo "Starting celery worker"
  sudo service notifications-api-celery-worker start
fi

if [ -e "/etc/init/notifications-api-celery-worker-sender.conf" ]
then
  echo "Starting celery worker"
  sudo service notifications-api-celery-worker-sender start
fi

if [ -e "/etc/init/notifications-api-celery-worker-db.conf" ]
then
  echo "Starting celery worker"
  sudo service notifications-api-celery-worker-db start
fi

if [ -e "/etc/init/notifications-api-celery-beat.conf" ]
then
  echo "Starting celery beat"
  sudo service notifications-api-celery-beat start
fi
