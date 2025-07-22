#!/bin/sh

set -ex

S3_BUCKET_URI="s3://dev-b-python-profiling-results/profile-run-$(date +%s)-final.svg"
LOCAL_PROFILE_PATH="/tmp/profile.svg"
PYSPY_LOG_PATH="/tmp/pyspy.errors.log"
PROFILE_DURATION=600  # Profile for 10 minutes
STARTUP_DELAY=1200    # Wait 20 minutes for app initialisation to complete

cleanup() {
  echo "FINAL UPLOAD: Checking for profile..."
  if [ -s "$LOCAL_PROFILE_PATH" ]; then
    echo "--- BEGIN PROFILE FILE (BASE64) ---"
    # This is our backup: print the base64 encoded file to the logs
    # If S3 fails, you can copy this text from the logs and decode it locally
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
# Start Gunicorn directly and send it to the background
/opt/venv/bin/gunicorn -c /home/vcap/app/gunicorn_config.py application &

# Get the PID of the Gunicorn Master Process
GUNICORN_PID=$!
echo "Gunicorn master process started with PID: ${GUNICORN_PID}"

echo "Waiting ${STARTUP_DELAY} seconds for workers to initialize..."
sleep "$STARTUP_DELAY"

echo "Starting py-spy to profile Gunicorn (PID: ${GUNICORN_PID}) for ${PROFILE_DURATION} seconds..."
echo "py-spy errors will be logged to ${PYSPY_LOG_PATH}"

# Attach py-spy, redirecting its standard error to a dedicated log file
# The '|| true' prevents the script from exiting if py-spy returns a non-zero code
py-spy record \
  -r 10 \
  -o "$LOCAL_PROFILE_PATH" \
  -s \
  -d "$PROFILE_DURATION" \
  -p "$GUNICORN_PID" \
  2> "$PYSPY_LOG_PATH" || true

echo "py-spy has finished. The cleanup function will now handle the upload."