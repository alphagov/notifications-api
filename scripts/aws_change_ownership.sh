#!/bin/bash

echo "Chown application to be owned by notify-api"
cd /home/notify-app/;
chown -R notify-app:govuk-notify-applications notifications-api
