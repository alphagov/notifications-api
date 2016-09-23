#!/usr/bin/env bash

set -eo pipefail

function stop
{
  service=$1
  if [ -e "/etc/init/${service}.conf" ]; then
    echo "stopping ${service}"
    if service ${service} stop; then
      echo "${service} stopped"
    else
      >&2 echo "Could not stop ${service}"
    fi
  fi
}

stop "notifications-api"
stop "notifications-api-celery-beat"
stop "notifications-api-celery-worker"
stop "notifications-api-celery-worker-sender"
stop "notifications-api-celery-worker-db"
