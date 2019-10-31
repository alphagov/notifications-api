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

# For every PID, check if it's still running. if it is, send the sigterm. then wait 9 seconds before sending sigkill
function on_exit {
  echo "multi worker app exiting"
  wait_time=0

  send_signal_to_celery_processes TERM

  # check if the apps are still running every second
  while [[ "$wait_time" -le "$TERMINATE_TIMEOUT" ]]; do
    get_celery_pids

    # look here for explanation regarding this syntax:
    # https://unix.stackexchange.com/a/298942/230401
    PROCESS_COUNT="${#APP_PIDS[@]}"
    if [[ "${PROCESS_COUNT}" -eq "0" ]]; then
        echo "No celery process is running any more, exiting"
        return 0
    fi

    let wait_time=wait_time+1
    sleep 1
  done

  send_signal_to_celery_processes KILL
}

function get_celery_pids {
  # get the PIDs of the process whose parent is the root process
  # print only pid and their command, get the ones with "celery" in their name
  # and keep only these PIDs

  set +o pipefail # so grep returning no matches does not premature fail pipe
  APP_PIDS=$(pgrep -P 1 | xargs ps -o pid=,command= -p | grep celery | cut -f1 -d/)
  set -o pipefail # pipefail should be set everywhere else
}

function send_signal_to_celery_processes {
  # refresh pids to account for the case that some workers may have terminated but others not
  get_celery_pids
  # send signal to all remaining apps
  echo ${APP_PIDS} | tr -d '\n' | tr -s ' ' | xargs echo "Sending signal ${1} to processes with pids: "
  echo ${APP_PIDS} | xargs kill -s ${1}
}

function start_application {
  echo "Starting application..."
  eval "$@"
  get_celery_pids
  echo "Application process pids: "${APP_PIDS}
}

function start_aws_logs_agent {
  echo "Starting aws logs agent..."
  exec aws logs push --region eu-west-1 --config-file /home/vcap/app/awslogs.conf &
  AWSLOGS_AGENT_PID=$!
  echo "AWS logs agent pid: ${AWSLOGS_AGENT_PID}"
}

function start_logs_tail {
  echo "Starting logs tail..."
  exec tail -n0 -f ${LOGS_DIR}/app.log.json &
  LOGS_TAIL_PID=$!
  echo "tail pid: ${LOGS_TAIL_PID}"
}

function ensure_celery_is_running {
  if [ "${APP_PIDS}" = "" ]; then
    echo "There are no celery processes running, this container is bad"

    echo "Exporting CF information for diagnosis"

    env | grep CF

    echo "Sleeping 15 seconds for logs to get shipped"

    sleep 15

    echo "Killing awslogs_agent and tail"
    kill -9 ${AWSLOGS_AGENT_PID}
    kill -9 ${LOGS_TAIL_PID}

    exit 1
  fi
}

function run {
  while true; do
    get_celery_pids

    ensure_celery_is_running

    for APP_PID in ${APP_PIDS}; do
        kill -0 ${APP_PID} 2&>/dev/null || return 1
    done
    kill -0 ${AWSLOGS_AGENT_PID} 2&>/dev/null || start_aws_logs_agent
    kill -0 ${LOGS_TAIL_PID} 2&>/dev/null || start_logs_tail
    sleep 1
  done
}

echo "Run script pid: $$"

check_params

trap "on_exit" EXIT TERM

configure_aws_logs

# The application has to start first!
start_application "$@"

start_aws_logs_agent
start_logs_tail

run
