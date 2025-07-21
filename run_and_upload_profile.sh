#!/bin/sh
set -e

# --- Configuration ---
LOCAL_PROFILE_PATH="/tmp/profile.svg"
PROFILE_DURATION=600 # 600 seconds = 10 minutes

echo "Starting py-spy to profile Gunicorn for ${PROFILE_DURATION} seconds..."
echo "Profile will be saved to ${LOCAL_PROFILE_PATH}"

# Run py-spy in the foreground for a fixed duration.
# It will automatically stop and save the file when the duration is up.
py-spy record \
  -r 10 \
  -o "$LOCAL_PROFILE_PATH" \
  -s \
  -n \
  -d "$PROFILE_DURATION" \
  -- \
  /opt/venv/bin/gunicorn -c /home/vcap/app/gunicorn_config.py application

# After py-spy exits and saves its file, the script will get here.
echo "py-spy has finished and saved the profile.svg."
echo "Container will now idle and can now be accessed to retrieve the profile.svg file."

# This infinite loop keeps the container alive after the profile is generated.
while true; do
  sleep 3600
done