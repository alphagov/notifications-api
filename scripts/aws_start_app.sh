#!/usr/bin/env bash

set -eo pipefail

function start
{
  service=$1
  if [ -e "/etc/init/${service}.conf" ]
  then
    echo "Starting ${service}"
    service ${service} start
  fi
}

start "notifications-api"
start "notifications-api-celery-worker"
start "notifications-api-celery-worker-sender"
start "notifications-api-celery-worker-db"
start "notifications-api-celery-beat"
