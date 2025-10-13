#!/bin/bash
set -Eeuo pipefail

BOLDGREEN="\033[1;32m"
ENDCOLOR="\033[0m"

# need to export these for the `flask db heads` subshell to pick them up
export FLASK_APP="application.py"
export NOTIFY_ENVIRONMENT="development"
MIGRATION_TEST_DATABASE_DB_NAME="migration_test"

# can’t use URI from environment variable because it uses a different protocol
POSTGRES_SERVER_URI=${POSTGRES_SERVER_URI:-"postgresql://postgres:postgres@localhost:5432/"}
# remove any existing db name, and replace with migration_test
POSTGRES_SERVER_URI="${POSTGRES_SERVER_URI%/*}/"
MIGRATION_TEST_DATABASE_URI="$POSTGRES_SERVER_URI$MIGRATION_TEST_DATABASE_DB_NAME"

# what is the database currently pointing at on main?
CURRENT_VERSION=$(curl -s https://raw.githubusercontent.com/alphagov/notifications-api/main/migrations/.current-alembic-head)

# what is the most recent version? note this depends on us only ever having one head
NEWEST_VERSION=$(flask db heads | tail -n 1 | cut -d " " -f 1)

# Always check that this script can connect to the database
psql $POSTGRES_SERVER_URI -c "BEGIN;COMMIT;"

if [[ "${CURRENT_VERSION}" == "${NEWEST_VERSION}" ]]; then
    echo "No migrations to check"
    exit 0;
fi

echo "Testing migrations on ${MIGRATION_TEST_DATABASE_URI}"


# when creating/dropping any existing test DB, we need to connect to the default database
psql $POSTGRES_SERVER_URI -c "drop database ${MIGRATION_TEST_DATABASE_DB_NAME}" || true
psql $POSTGRES_SERVER_URI -c "create database ${MIGRATION_TEST_DATABASE_DB_NAME}"

echo -e "${BOLDGREEN}======== running upgrade (logs hidden) ========${ENDCOLOR}"

SQLALCHEMY_DATABASE_URI=$MIGRATION_TEST_DATABASE_URI flask db upgrade > /dev/null 2>&1

# make sure downgrade can run succesfully
echo -e "${BOLDGREEN}============== running downgrade ==============${ENDCOLOR}"
SQLALCHEMY_DATABASE_URI=$MIGRATION_TEST_DATABASE_URI flask db downgrade $CURRENT_VERSION

# make sure downgrade has left everything okay
echo -e "${BOLDGREEN}============ running upgrade again ============${ENDCOLOR}"
SQLALCHEMY_DATABASE_URI=$MIGRATION_TEST_DATABASE_URI flask db upgrade

psql $POSTGRES_SERVER_URI -c "drop database ${MIGRATION_TEST_DATABASE_DB_NAME}"

echo -e "${BOLDGREEN}=================== success ===================${ENDCOLOR}"
