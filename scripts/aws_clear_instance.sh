#!/bin/bash

echo "Removing application and dependencies"

if [ -d "/home/notify-app/notifications-api" ]; then
    # Remove and re-create the directory
    rm -rf /home/notify-app/notifications-api
    mkdir -vp /home/notify-app/notifications-api
fi

