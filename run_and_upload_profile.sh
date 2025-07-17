#!/bin/sh
set -e

# --- Configuration ---
S3_BUCKET_URI_PART="s3://dev-b-python-profiling-results"
# Construct the full, unique S3 URI for this run
S3_BUCKET_URI="${S3_BUCKET_URI_PART}/profile-run-$(date +%s)"
LOCAL_PROFILE_PATH="/tmp/profile.svg"
PYSPY_LOG_PATH="/tmp/pyspy.errors.log" # Dedicated error log for py-spy
UPLOAD_INTERVAL=900 # 900 seconds = 15 minutes

# --- Main Logic ---
echo "Starting periodic S3 upload every ${UPLOAD_INTERVAL} seconds..."

# Start a background loop to upload the file periodically
(
  upload_count=0
  while true; do
    sleep "$UPLOAD_INTERVAL"
    upload_count=$((upload_count + 1))
    echo "PERIODIC UPLOAD: Checking for profile file..."
    if [ -s "$LOCAL_PROFILE_PATH" ]; then
      S3_PERIODIC_URI="${S3_BUCKET_URI}-part-${upload_count}.svg"
      echo "PERIODIC UPLOAD: Found profile file, uploading to ${S3_PERIODIC_URI}..."
      aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_PERIODIC_URI"
      echo "PERIODIC UPLOAD: Upload complete."
    else
      echo "PERIODIC UPLOAD: Profile file not found or is empty."
    fi
  done
) &

# This is the cleanup function that will run when the script exits.
cleanup() {
  S3_FINAL_URI="${S3_BUCKET_URI}-final.svg"
  echo "FINAL UPLOAD: Process exited. Uploading profile to ${S3_FINAL_URI}..."
  if [ -s "$LOCAL_PROFILE_PATH" ]; then
    aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_FINAL_URI"
    echo "FINAL UPLOAD: Upload complete."
  else
    echo "FINAL UPLOAD: Profile file not found or is empty. Skipping upload."
  fi
}

trap cleanup EXIT

echo "Starting py-spy to profile Gunicorn..."
echo "Output will be saved to ${LOCAL_PROFILE_PATH}"
echo "py-spy errors will be logged to ${PYSPY_LOG_PATH}"

# 1. Redirect py-spy's stderr (2) to its log file.
# 2. Use 'sh -c' to run gunicorn in its own shell.
# 3. In that subshell, redirect gunicorn's stderr (2) to its stdout (1).
py-spy record -r 10 -o "$LOCAL_PROFILE_PATH" -s -n \
  2> "$PYSPY_LOG_PATH" \
  -- \
  sh -c 'exec gunicorn -c /home/vcap/app/gunicorn_config.py application 2>&1' &


# Get the PID of the py-spy process
PYSPY_PID=$!

# Wait for the process to finish.
# '|| true' ensures the script doesn't exit if py-spy crashes, so you can debug.
wait $PYSPY_PID || true

echo "py-spy process has exited. Script will now terminate, triggering final upload check."