#!/bin/bash
set -Eeuo pipefail

BOLDGREEN="\033[1;32m"
ENDCOLOR="\033[0m"

FLASK_APP="application.py"
NOTIFY_ENVIRONMENT="development"
MIGRATION_TEST_DATABASE_DB_NAME="migration_test"

MIGRATION_TEST_DATABASE_URI=${SQLALCHEMY_DATABASE_URI:-"postgresql://postgres:postgres@localhost/"}
# replace whatever database name the outside env has with the test database's db
MIGRATION_TEST_DATABASE_URI="${MIGRATION_TEST_DATABASE_URI%/*}/${MIGRATION_TEST_DATABASE_DB_NAME}"

# what is the database currently pointing at on main?
CURRENT_VERSION=$(curl -s https://raw.githubusercontent.com/alphagov/notifications-api/main/migrations/.current-alembic-head)

# what is the most recent version? note this depends on us only ever having one head
NEWEST_VERSION=$(flask db heads | tail -n 1 | cut -d " " -f 1)

if [[ "${CURRENT_VERSION}" == "${NEWEST_VERSION}" ]]; then
    echo "No migrations to check"
    exit 0;
fi

echo "Testing migrations on ${MIGRATION_TEST_DATABASE_URI}"

# delete any existing test DB
psql -c "drop database ${MIGRATION_TEST_DATABASE_DB_NAME}" || true
psql -c "create database ${MIGRATION_TEST_DATABASE_DB_NAME}"

echo -e "${BOLDGREEN}======== running upgrade (logs hidden) ========${ENDCOLOR}"

SQLALCHEMY_DATABASE_URI=$MIGRATION_TEST_DATABASE_URI flask db upgrade > /dev/null 2>&1

# make sure downgrade can run succesfully
echo -e "${BOLDGREEN}============== running downgrade ==============${ENDCOLOR}"
SQLALCHEMY_DATABASE_URI=$MIGRATION_TEST_DATABASE_URI flask db downgrade $CURRENT_VERSION

# make sure downgrade has left everything okay
echo -e "${BOLDGREEN}============ running upgrade again ============${ENDCOLOR}"
SQLALCHEMY_DATABASE_URI=$MIGRATION_TEST_DATABASE_URI flask db upgrade

psql -c "drop database ${MIGRATION_TEST_DATABASE_DB_NAME}"

echo -e "${BOLDGREEN}=================== success ===================${ENDCOLOR}"
