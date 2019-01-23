#!/bin/bash

set -e -o pipefail

readonly LOGS_DIR="/home/vcap/logs"

echo "Run script pid: $$"

if [ -z "${NOTIFY_APP_NAME}" ]; then
  echo "You must set NOTIFY_APP_NAME"
  exit 1
fi

if [ -z "${CW_APP_NAME}" ]; then
  CW_APP_NAME=${NOTIFY_APP_NAME}
fi

echo "Configuring logs"
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

cat <<EOF > /home/vcap/app/supervisor.conf
[supervisord]
nodaemon=true

[program:supervised]
process_name=supervised_%(process_num)02d
command=$@
numprocs=${NUM_PROCESSES:-3}
numprocs_start=1
autorestart=true
startsecs=15
stdout_logfile=${LOGS_DIR}/app.log.json
stderr_logfile=${LOGS_DIR}/logs/app.log.json
stdout_logfile_maxbytes=0
stdout_logfile_backups=0
stderr_logfile_maxbytes=0
stderr_logfile_backups=0
stdout_events_enabled=true
stderr_events_enabled=true

[program:awslogs]
process_name=supervised_%(process_num)02d
command=aws logs push --region eu-west-1 --config-file /home/vcap/app/awslogs.conf
autorestart=true
startsecs=15
stdout_logfile=${LOGS_DIR}/app.log.json
stderr_logfile=${LOGS_DIR}/logs/app.log.json
stdout_logfile_maxbytes=0
stdout_logfile_backups=0
stderr_logfile_maxbytes=0
stderr_logfile_backups=0
stdout_events_enabled=true
stderr_events_enabled=true

[eventlistener:shootself]
command=python kill_supervisor.py
events=PROCESS_STATE_FATAL,PROCESS_STATE_UNKNOWN
stdout_events_enabled=true
stderr_events_enabled=true

[eventlistener:stdout]
command=supervisor_stdout
buffer_size=100
events=PROCESS_LOG
result_handler=supervisor_stdout:event_handler
EOF

supervisord -n -c /home/vcap/app/supervisor.conf
