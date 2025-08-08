#!/bin/sh

set -e

# --- Configuration ---
S3_BUCKET_URI="s3://dev-b-python-profiling-results/python313/celery-profile-$(date +%s).json"
LOCAL_PROFILE_PATH="/tmp/celery-profile.json"
PROFILE_DURATION=600

# --- Cleanup Function ---
# Ensures the profile is uploaded when the script exits.
cleanup() {
  echo "PROFILING SCRIPT EXITING..."
  if [ -s "$LOCAL_PROFILE_PATH" ]; then
    echo "UPLOAD: Found profile, attempting to upload to ${S3_BUCKET_URI}..."
    aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_BUCKET_URI" || echo "UPLOAD FAILED"
  else
    echo "UPLOAD: Profile file not found or empty."
  fi
}
trap cleanup EXIT


# --- Application Startup ---
echo "Starting Celery worker in the background..."
# This command starts the Celery worker process.
/opt/venv/bin/celery --quiet -A run_celery.notify_celery worker \
  --logfile=/dev/null \
  --concurrency=${CONCURRENCY:-4} \
  "$@" &
CELERY_PID=$!
echo "Celery worker started with PID: ${CELERY_PID}"
sleep 1200


# --- Profiling ---
echo "Starting py-spy to profile Celery Worker (PID: ${CELERY_PID})..."
py-spy record \
  --format speedscope \
  -r 50 \
  --nonblocking \
  -o "$LOCAL_PROFILE_PATH" \
  -d "$PROFILE_DURATION" \
  -p "$CELERY_PID"


# --- Keep Container Alive ---
echo "py-spy finished. Waiting for worker to exit."
# The 'wait' command is crucial. It pauses the script and makes the
# Celery worker the process that controls the container's lifecycle.
echo "py-spy has finished. The cleanup function will now handle the upload."
sleep 1800 # ensure that that the task is not terminated even though the script has completed execution.
