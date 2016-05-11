#!/bin/bash -x

# This script lives in each of the upstream repos. Add this to .travis.yml to
# run after each successful build (assuming that the script is in the root of
# the repo):
#   after_success:
#     - ./trigger-dependent-build
#

case $TRAVIS_BRANCH in
  master|staging|live)
    echo "Triggering dependent build for $TRAVIS_BRANCH"
    curl -vvv -s -X POST -H "Content-Type: application/json" -H "Accept: application/json" -H "Travis-API-Version: 3" -H "Authorization: token $auth_token" -d '{"request":{"branch":"master","config":{"env":{"global":["ENVIRONMENT='$TRAVIS_BRANCH'"]}}}}' https://api.travis-ci.org/repo/alphagov%2Fnotifications-functional-tests/requests
    ;;
  *)
    echo "Not triggering dependent build for $TRAVIS_BRANCH"
    ;;
esac
