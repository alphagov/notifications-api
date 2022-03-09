#!/bin/bash
set -eu

DOCKER_IMAGE_NAME=notifications-api

source environment.sh

# this script should be run from within your virtualenv so you can access the aws cli
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-"$(aws configure get aws_access_key_id)"}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-"$(aws configure get aws_secret_access_key)"}
SQLALCHEMY_DATABASE_URI="postgresql://postgres@host.docker.internal/notification_api"
REDIS_URL="redis://host.docker.internal:6379"
API_HOST_NAME="http://host.docker.internal:6011"

docker run -it --rm \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e SQLALCHEMY_DATABASE_URI=$SQLALCHEMY_DATABASE_URI \
  -e REDIS_ENABLED=${REDIS_ENABLED:-0} \
  -e REDIS_URL=$REDIS_URL \
  -e API_HOST_NAME=$API_HOST_NAME \
  -v $(pwd):/home/vcap/app \
  ${DOCKER_IMAGE_NAME} \
  ${@}
