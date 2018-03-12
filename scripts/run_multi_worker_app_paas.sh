#!/bin/bash

set -e -o pipefail

TERMINATE_TIMEOUT=9
readonly LOGS_DIR="/home/vcap/logs"

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
  # create files so that aws logs agent doesn't complain
  touch ${LOGS_DIR}/gunicorn_error.log
  touch ${LOGS_DIR}/app.log.json

  aws configure set plugins.cwlogs cwlogs

  cat > /home/vcap/app/awslogs.conf << EOF
[general]
state_file = ${LOGS_DIR}/awslogs-state

[${LOGS_DIR}/app.log]
file = ${LOGS_DIR}/app.log.json
log_group_name = paas-${CW_APP_NAME}-application
log_stream_name = {hostname}

[${LOGS_DIR}/gunicorn_error.log]
file = ${LOGS_DIR}/gunicorn_error.log
log_group_name = paas-${CW_APP_NAME}-gunicorn
log_stream_name = {hostname}
EOF
}

# For every PID, check if it's still running
# if it is, send the sigterm
function on_exit {
  wait_time=0
  while true; do
    # refresh pids to account for the case that
    # some workers may have terminated but others not
    get_celery_pids

    # look here for explanation regarding this syntax:
    # https://unix.stackexchange.com/a/298942/230401
    PROCESS_COUNT="${#APP_PIDS[@]}"
    if [[ "${PROCESS_COUNT}" -eq "0" ]]; then
        echo "No more .pid files found, exiting"
        break
    fi

    echo "Terminating celery processes with pids "${APP_PIDS}
    for APP_PID in ${APP_PIDS}; do
      # if TERMINATE_TIMEOUT is reached, send SIGKILL
      if [[ "$wait_time" -ge "$TERMINATE_TIMEOUT" ]]; then
        echo "Timeout reached, killing process with pid ${APP_PID}"
        kill -9 ${APP_PID} || true
        continue
      else
        echo "Timeout not reached yet, checking " ${APP_PID}
        # else, if process is still running send SIGTERM
        if [[ $(kill -0 ${APP_PID} 2&>/dev/null) ]]; then
          echo "Terminating celery process with pid ${APP_PID}"
          kill ${APP_PID} || true
        fi
      fi
    done
    let wait_time=wait_time+1
    sleep 1
  done
}

function get_celery_pids {
  if [[ $(ls /home/vcap/app/celery*.pid) ]]; then
    APP_PIDS=`cat /home/vcap/app/celery*.pid`
  else
    APP_PIDS=()
  fi
}

function start_application {
  eval "$@"
  get_celery_pids
  echo "Application process pids: "${APP_PIDS}
}

function start_aws_logs_agent {
  exec aws logs push --region eu-west-1 --config-file /home/vcap/app/awslogs.conf &
  AWSLOGS_AGENT_PID=$!
  echo "AWS logs agent pid: ${AWSLOGS_AGENT_PID}"
}

function run {
  while true; do
    get_celery_pids
    for APP_PID in ${APP_PIDS}; do
        kill -0 ${APP_PID} 2&>/dev/null || return 1
    done
    kill -0 ${AWSLOGS_AGENT_PID} 2&>/dev/null || start_aws_logs_agent
    sleep 1
  done
}

echo "Run script pid: $$"

check_params

trap "on_exit" EXIT

configure_aws_logs

# The application has to start first!
start_application "$@"

start_aws_logs_agent

run
