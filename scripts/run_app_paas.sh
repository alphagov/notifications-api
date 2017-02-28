#!/bin/bash

set -e -o pipefail

TERMINATE_TIMEOUT=30

function check_params {
  if [ -z "${NOTIFY_APP_NAME}" ]; then
    echo "You must set NOTIFY_APP_NAME"
    exit 1
  fi

  if [ -z "${CW_APP_NAME}" ]; then
    CW_APP_NAME=${NOTIFY_APP_NAME}
  fi
}

function configure_aws_logs {
  aws configure set plugins.cwlogs cwlogs

  export AWS_ACCESS_KEY_ID=$(echo ${VCAP_SERVICES} | jq -r '.["user-provided"][]|select(.name=="notify-aws")|.credentials.aws_access_key_id')
  export AWS_SECRET_ACCESS_KEY=$(echo ${VCAP_SERVICES} | jq -r '.["user-provided"][]|select(.name=="notify-aws")|.credentials.aws_secret_access_key')

  cat > /home/vcap/app/awslogs.conf << EOF
[general]
state_file = /home/vcap/logs/awslogs-state

[/home/vcap/logs/app-stdout.log]
file = /home/vcap/logs/app-stdout.log*
log_group_name = paas-${CW_APP_NAME}-application
log_stream_name = {hostname}-stdout

[/home/vcap/logs/app-stderr.log]
file = /home/vcap/logs/app-stderr.log*
log_group_name = paas-${CW_APP_NAME}-application
log_stream_name = {hostname}-stderr
EOF
}

function on_exit {
  echo "Terminating application process with pid ${APP_PID}"
  kill ${APP_PID} || true
  n=0
  while (kill -0 ${APP_PID} 2&>/dev/null); do
    echo "Application is still running.."
    sleep 1
    let n=n+1
    if [ "$n" -ge "$TERMINATE_TIMEOUT" ]; then
      echo "Timeout reached, killing process with pid ${APP_PID}"
      kill -9 ${APP_PID} || true
      break
    fi
  done
  echo "Application process terminated, waiting 10 seconds"
  sleep 10
  echo "Terminating remaining subprocesses.."
  kill 0
}

function start_appplication {
  exec "$@" 2>/home/vcap/logs/app-stderr.log | while read line; do echo $line; echo $line >> /home/vcap/logs/app-stdout.log.`date +%Y-%m-%d`; done &
  LOGGER_PID=$!
  APP_PID=`jobs -p`
  echo "Logger process pid: ${LOGGER_PID}"
  echo "Application process pid: ${APP_PID}"
}

function start_aws_logs_agent {
  exec aws logs push --region eu-west-1 --config-file /home/vcap/app/awslogs.conf &
  AWSLOGS_AGENT_PID=$!
  echo "AWS logs agent pid: ${AWSLOGS_AGENT_PID}"
}

function run {
  while true; do
    kill -0 ${APP_PID} 2&>/dev/null || break
    kill -0 ${LOGGER_PID} 2&>/dev/null || break
    kill -0 ${AWSLOGS_AGENT_PID} 2&>/dev/null || start_aws_logs_agent
    sleep 1
  done
}

echo "Run script pid: $$"

check_params

trap "on_exit" EXIT

configure_aws_logs

# The application has to start first!
start_appplication "$@"

start_aws_logs_agent

run
