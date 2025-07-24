#!/bin/sh

set -ex

S3_BUCKET_URI="s3://dev-b-python-profiling-results/python311/profile-run-$(date +%s)-final.svg"
LOCAL_PROFILE_PATH="/tmp/profile_311.svg"
PYSPY_LOG_PATH="/tmp/pyspy.errors.log"
PROFILE_DURATION=600
STARTUP_DELAY=120 # shorter delay to wait for workers to spawn which we want py-spy to attach to
APP_INIT_TIMEOUT=300 # Wait for app initialisation to complete

cleanup() {
  echo "FINAL UPLOAD: Checking for profile..."
  if [ -s "$LOCAL_PROFILE_PATH" ]; then
    echo "--- BEGIN PROFILE FILE (BASE64) ---"
    # This is our backup: print the base64 encoded file to the logs
    base64 "$LOCAL_PROFILE_PATH"
    echo "--- END PROFILE FILE (BASE64) ---"

    echo "FINAL UPLOAD: Found profile file, attempting to upload to ${S3_BUCKET_URI}..."
    # Attempt the upload. The script will exit if this fails due to 'set -e'
    aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_BUCKET_URI"
    echo "FINAL UPLOAD: AWS CLI command finished successfully."
  else
    echo "FINAL UPLOAD: Profile file not found or is empty. Skipping upload."
  fi

  # Also upload the py-spy error log for debugging
  if [ -s "$PYSPY_LOG_PATH" ]; then
    echo "Uploading py-spy error log..."
    aws s3 cp "$PYSPY_LOG_PATH" "${S3_BUCKET_URI}.errors.log"
  fi
}

trap cleanup EXIT

echo "Starting Gunicorn in the background..."
/opt/venv/bin/gunicorn -c /home/vcap/app/gunicorn_config.py application &
MASTER_PID=$!
echo "Gunicorn master process started with PID: ${MASTER_PID}"

echo "Waiting for a Gunicorn worker process to appear (child of ${MASTER_PID})..."
sleep "$STARTUP_DELAY" # Give workers a moment to spawn

# Find a worker PID. pgrep finds processes with a given parent PID.
WORKER_PID=$(pgrep -P "$MASTER_PID" | head -n 1)

if [ -z "$WORKER_PID" ]; then
  echo "Error: Could not find a Gunicorn worker process. Exiting."
  exit 1
fi

echo "Found Gunicorn worker with PID: ${WORKER_PID}"
echo "Waiting ${APP_INIT_TIMEOUT} seconds for app to fully initialize..."
sleep "$APP_INIT_TIMEOUT"

echo "Starting py-spy to profile(python 3.11) Gunicorn Worker (PID: ${WORKER_PID}) for ${PROFILE_DURATION} seconds..."
echo "py-spy errors will be logged to ${PYSPY_LOG_PATH}"

# We target the worker PID directly. The -s flag is removed as it's no longer needed.
py-spy record \
  -r 10 \
  -o "$LOCAL_PROFILE_PATH" \
  -d "$PROFILE_DURATION" \
  -p "$WORKER_PID" \
  2> "$PYSPY_LOG_PATH" || true

echo "py-spy has finished. The cleanup function will now handle the upload."
sleep 1800 # ensure that that the task is not terminated even though the script has completed execution.