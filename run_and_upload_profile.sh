#!/bin/sh

set -ex

LOCAL_PROFILE_PATH="/tmp/python-profile.json"
PROFILE_DURATION=600
STARTUP_DELAY=120 # shorter delay to wait for workers to spawn which we want py-spy to attach to
APP_WARM_UP=1200 # Wait for app initialisation to complete

echo "Starting Gunicorn in the background..."
/opt/venv/bin/gunicorn -c /home/vcap/app/gunicorn_config.py application &
MASTER_PID=$!
echo "Gunicorn master process started with PID: ${MASTER_PID}"

echo "Waiting ${APP_WARM_UP} secs for app to warm up before profiling starts....."
sleep 1200

# --- Profiling ---
py-spy record \
  --format flamegraph \
  -r 80 \
  -o "$LOCAL_PROFILE_PATH" \
  -d "$PROFILE_DURATION" \
  -p "$MASTER_PID" \
  --subprocesses

echo "py-spy finished. Profile saved to ${LOCAL_PROFILE_PATH}"


# --- Keep Container Alive ---
echo "Keeping container alive for manual inspection/retrieval."
echo "You can now ssh into the container and retrieve the profile from ${LOCAL_PROFILE_PATH}"
echo "Script is waiting for Gunicorn (PID: $MASTER_PID) to exit."
# This wait command will block indefinitely (as Gunicorn is running),
# keeping the script and container alive until you manually stop it
# or Gunicorn crashes. The 'trap cleanup' will run on exit.
wait "$MASTER_PID"
