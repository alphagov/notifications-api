#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
S3_BUCKET_URI="s3://dev-b-python-profiling-results/profile-313-$(date +%s).svg"
LOCAL_PROFILE_PATH="/tmp/profile.svg"

# --- Main Logic ---
echo "Starting py-spy to profile Gunicorn..."
echo "Output will be saved to ${LOCAL_PROFILE_PATH}"

# Trap the EXIT signal to ensure the upload happens even if the container is stopped.
cleanup() {
  echo "Process exited. Uploading profile to S3..."
  if [ -f "$LOCAL_PROFILE_PATH" ]; then
    aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_BUCKET_URI"
    echo "Upload complete."
  else
    echo "Profile file not found at ${LOCAL_PROFILE_PATH}. Skipping upload."
  fi
}

trap cleanup EXIT

# Start py-spy, which will in turn start Gunicorn.
py-spy record -r 13 -o "$LOCAL_PROFILE_PATH" -s -n -- gunicorn -c /home/vcap/app/gunicorn_config.py application