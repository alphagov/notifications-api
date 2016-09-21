#!/bin/bash

set -eo pipefail

echo "Chown application to be owned by notify-app"

cd /home/notify-app/;
chown -R notify-app:govuk-notify-applications notifications-api
