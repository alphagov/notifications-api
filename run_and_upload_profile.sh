# --- Configuration ---
S3_BUCKET_URI="s3://dev-b-python-profiling-results/profile-run-$(date +%s)-final.svg"
LOCAL_PROFILE_PATH="/tmp/profile.svg"
PROFILE_DURATION=600 # 600 seconds = 10 minutes

# --- Main Logic ---
cleanup() {
  echo "FINAL UPLOAD: Process exited. Checking for profile..."
  if [ -s "$LOCAL_PROFILE_PATH" ]; then
    echo "FINAL UPLOAD: Found profile file, uploading to ${S3_BUCKET_URI}..."
    aws s3 cp "$LOCAL_PROFILE_PATH" "$S3_BUCKET_URI"
    echo "FINAL UPLOAD: Upload complete."
  else
    echo "FINAL UPLOAD: Profile file not found. Skipping upload."
  fi
}
trap cleanup EXIT

echo "Starting py-spy to profile Gunicorn for ${PROFILE_DURATION} seconds..."

# Run py-spy in the foreground for a fixed duration.
# It will automatically stop and save the file when the duration is up.
py-spy record \
  -r 15 \
  -o "$LOCAL_PROFILE_PATH" \
  -s \
  -n \
  -d "$PROFILE_DURATION" \
  -- \
  gunicorn -c /home/vcap/app/gunicorn_config.py application