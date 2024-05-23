#!/bin/bash
set -Eeuo pipefail

if ! [[ -x "$(command -v squawk)" ]]; then
    echo "ERR: Squawk not found. Install with npm install -g squawk-cli" >&2
    exit 1;
fi


# ensure main is up-to-date
git fetch origin main:main

FILES_COMMITTED_TO_BRANCH=$(git diff --name-only main -- migrations/versions/)
UNADDED_FILES=$(git ls-files --others --exclude-standard migrations/versions)

if [[ -z "${FILES_COMMITTED_TO_BRANCH}" && -z "${UNADDED_FILES}" ]]; then
    # no edits to migrations, either added or not added
    echo "No migrations"
    exit 0;
fi

source environment.sh

# what is the database currently pointing at on master?
CURRENT_VERSION=$(git show main:migrations/.current-alembic-head)
# what is the most recent version? note this depends on us only ever having one head
NEWEST_VERSION=$(flask db heads | tail -n 1 | cut -d " " -f 1)

if [[ "${CURRENT_VERSION}" == "${NEWEST_VERSION}" ]]; then
    # there's changes to migrations, but no new version to test against?
    # has someone modified an existing migration?
    echo "Migrations found but can't work out what's different to master"
    exit 0;
fi

# tail -n +2 removes the first line of output - the stupid "logging configured" line
flask db upgrade --sql $CURRENT_VERSION:$NEWEST_VERSION | tail -n +2 > /tmp/upgrade.sql

echo
# postgres version should match `rds_engine_version` in notifications-aws/terraform/notify-infra/tfvars/globals.tfvars
squawk /tmp/upgrade.sql --pg-version="15.5"
