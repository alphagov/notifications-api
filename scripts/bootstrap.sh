#!/bin/bash
#
# Bootstrap virtualenv environment and postgres databases locally.
#
# NOTE: This script expects to be run from the project root with
# ./scripts/bootstrap.sh

set -o pipefail

function display_result {
  RESULT=$1
  EXIT_STATUS=$2
  TEST=$3

  if [ $RESULT -ne 0 ]; then
    echo -e "\033[31m$TEST failed\033[0m"
    exit $EXIT_STATUS
  else
    echo -e "\033[32m$TEST passed\033[0m"
  fi
}

if [ ! $VIRTUAL_ENV ]; then
  virtualenv -p python3 ./venv
  . ./venv/bin/activate
fi

# we need the version file to exist otherwise the app will blow up
make generate-version-file

# Install Python development dependencies
pip3 install -r requirements_for_test.txt

# Create Postgres databases
createdb notification_api
createdb test_notification_api

# Upgrade databases
source environment.sh
python application.py db upgrade
