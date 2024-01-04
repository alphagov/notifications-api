#!/bin/bash
set -eu

DOCKER_IMAGE_NAME=notifications-api

source environment.sh

# this script should be run from within your virtualenv so you can access the aws cli
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-"$(aws configure get aws_access_key_id)"}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-"$(aws configure get aws_secret_access_key)"}
SQLALCHEMY_DATABASE_URI=${SQLALCHEMY_DATABASE_URI:-"postgresql://postgres@host.docker.internal/notification_api"}
REDIS_URL=${REDIS_URL:-"redis://host.docker.internal:6379"}
API_HOST_NAME=${API_HOST_NAME:-"http://host.docker.internal:6011"}
API_HOST_NAME_INTERNAL=${API_HOST_NAME_INTERNAL:-"http://host.docker.internal:6011"}

# Only expose port 6011 if we're running the API - anything else is celery which shouldn't bind the port.
# This lets us run celery via docker and the API locally.
if [[ "${@}" == "api" || "${@}" == "api-local" ]]; then
  EXPOSED_PORTS="-e PORT=6011 -p 6011:6011"
else
  EXPOSED_PORTS=""
fi

docker run -it --rm \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -e SQLALCHEMY_DATABASE_URI=$SQLALCHEMY_DATABASE_URI \
  -e REDIS_ENABLED=${REDIS_ENABLED:-0} \
  -e REDIS_URL=$REDIS_URL \
  -e API_HOST_NAME=$API_HOST_NAME \
  -e API_HOST_NAME_INTERNAL=$API_HOST_NAME_INTERNAL \
  -e NOTIFY_ENVIRONMENT=$NOTIFY_ENVIRONMENT \
  -e MMG_API_KEY=$MMG_API_KEY \
  -e FIRETEXT_API_KEY=$FIRETEXT_API_KEY \
  -e NOTIFICATION_QUEUE_PREFIX=$NOTIFICATION_QUEUE_PREFIX \
  -e FLASK_APP=$FLASK_APP \
  -e FLASK_DEBUG=$FLASK_DEBUG \
  -e WERKZEUG_DEBUG_PIN=$WERKZEUG_DEBUG_PIN \
  ${EXPOSED_PORTS} \
  -v $(pwd):/home/vcap/app \
  ${DOCKER_IMAGE_NAME} \
  ${@}
