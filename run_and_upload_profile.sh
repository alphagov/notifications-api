#!/bin/sh

set -e

# --- Configuration ---
S3_BUCKET_URI="s3://dev-e-celery-profiling-results/celery-profile-$(date +%s).json"
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
# This command starts the Celery worker (master) process.
/opt/venv/bin/celery --quiet -A run_celery.notify_celery worker \
  --logfile=/dev/null \
  --concurrency=${CONCURRENCY:-4} \
  "$@" &
MAIN_CELERY_PID=$!
echo "Celery worker (master) started with PID: ${MAIN_CELERY_PID}"

# --- Warm-up Period ---
# Wait for the application to be in a steady state before profiling.
echo "Allowing application to warm up for 1200 seconds..."
sleep 1200

# --- Profiling ---
echo "Starting py-spy to profile Celery Master (PID: ${MAIN_CELERY_PID}) and all subprocesses..."
py-spy record \
  --format speedscope \
  -r 50 \
  -o "$LOCAL_PROFILE_PATH" \
  -d "$PROFILE_DURATION" \
  -p "$MAIN_CELERY_PID" \
  --subprocesses # <-- profiles the master process and all its worker children

# --- Keep Container Alive ---
echo "py-spy finished. Waiting for worker (PID: $MAIN_CELERY_PID) to exit."
# Keep the container alive until the Celery process itself terminates.
wait "$MAIN_CELERY_PID"