#!/bin/bash


function error_exit
{
	echo "$1" 1>&2
	exit 0
}

if [ -e "/etc/init/notifications-api.conf" ]; then
    echo "stopping notifications-api"
    if sudo service notifications-api stop; then
        echo "notifications-api stopped"
    else
        error_exit "Could not stop notifications-api"
    fi
fi

if [ -e "/etc/init/notifications-api-celery-beat.conf" ]; then
    echo "stopping notifications-api-celery-beat"
    if sudo service notifications-api-celery-beat stop; then
        echo "notifications-api stopped"
    else
        error_exit "Could not stop notifications-celery-beat"
    fi
fi

if [ -e "/etc/init/notifications-api-celery-worker.conf" ]; then
    echo "stopping notifications-api-celery-worker"
    if sudo service notifications-api-celery-worker stop; then
        echo "notifications-api stopped"
    else
        error_exit "Could not stop notifications-celery-worker"
    fi
fi
