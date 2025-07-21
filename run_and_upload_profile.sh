#!/bin/sh
set -e

# --- Configuration ---
S3_BUCKET_URI="s3://dev-b-python-profiling-results/profile-run-$(date +%s)-final.svg"
LOCAL_PROFILE_PATH="/tmp/profile.svg"
PROFILE_DURATION=600  # Profile for 10 minutes
STARTUP_DELAY=60    # Wait 20 minutes for app initialisation to complete

# --- Main Logic ---
cleanup() {
  echo "FINAL UPLOAD: Checking for profile..."
  if [ -s "$LOCAL_PROFILE_PATH" ]; then
    echo "FINAL UPLOAD: Found profile file, uploading to ${S3_BUCKET_URI}..."
    aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_BUCKET_URI"
    echo "FINAL UPLOAD: Upload complete."
  else
    echo "FINAL UPLOAD: Profile file not found. Skipping upload."
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

echo "Starting py-spy to profile the running Gunicorn processes for ${PROFILE_DURATION} seconds..."
# Attach py-spy to the running Gunicorn master process using its PID
py-spy record \
  -r 10 \
  -o "$LOCAL_PROFILE_PATH" \
  -s \
  -d "$PROFILE_DURATION" \
  -p "$GUNICORN_PID"

echo "py-spy has finished and saved the profile.svg. Script will now exit."