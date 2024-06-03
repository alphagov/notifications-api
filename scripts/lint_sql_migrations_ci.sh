#!/bin/bash
set -Eeuo pipefail

export FLASK_APP=application.py
export NOTIFY_ENVIRONMENT="development"

# what is the database currently pointing at on main?
CURRENT_VERSION=$(curl -s https://raw.githubusercontent.com/alphagov/notifications-api/main/migrations/.current-alembic-head)

# what is the most recent version? note this depends on us only ever having one head
NEWEST_VERSION=$(flask db heads | tail -n 1 | cut -d " " -f 1)

if [[ "${CURRENT_VERSION}" == "${NEWEST_VERSION}" ]]; then
    echo "No migrations to check"
    exit 0;
fi

# tail -n +2 removes the first "logging configured" line of the output
flask db upgrade --sql $CURRENT_VERSION:$NEWEST_VERSION | tail -n +2 > /tmp/upgrade.sql

echo

# postgres version should match `rds_engine_version` in notifications-aws/terraform/notify-infra/tfvars/globals.tfvars
squawk /tmp/upgrade.sql --pg-version="15.5"
