#!/bin/bash

set -e

source environment.sh
celery -A run_celery.notify_celery worker --pidfile="/tmp/celery-3.pid" --loglevel=INFO --concurrency=10 --logfile=/tmp/celery.log
