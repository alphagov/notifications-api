#!/usr/bin/env bash

set -eo pipefail

echo "Run database migrations"

cd /home/notify-app/notifications-api;
python3 db.py db upgrade
