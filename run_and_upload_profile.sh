#!/bin/sh

set -e

# --- Configuration ---
LOCAL_PROFILE_PATH="/tmp/celery-profile.json"
PROFILE_DURATION=600

# --- Application Startup ---
echo "Starting Celery worker in the background..."
# This command starts the Celery worker process.
/opt/venv/bin/celery --quiet -A run_celery.notify_celery worker \
  --logfile=/dev/null \
  --concurrency=${CONCURRENCY:-4} \
  "$@" &
MAIN_CELERY_PID=$!
echo "Celery worker started with PID: ${MAIN_CELERY_PID}"

# 'pgrep -P' finds processes with the specified parent PID. We take the first one.
WORKER_PID=$(pgrep -P "$MAIN_CELERY_PID" | head -n 1)

sleep 1200

# --- Profiling ---
echo "Starting py-spy to profile Celery Worker (PID: ${WORKER_PID})..."
py-spy record \
  --format speedscope \
  -r 100 \
  -o "$LOCAL_PROFILE_PATH" \
  -d "$PROFILE_DURATION" \
  -p "$WORKER_PID"


# --- Keep Container Alive ---
echo "py-spy finished. Waiting for worker to exit."
# The 'wait' command is crucial. It pauses the script and makes the
# Celery worker the process that controls the container's lifecycle.
echo "py-spy has finished."
sleep 1800 # ensure that that the task is not terminated even though the script has completed execution.
