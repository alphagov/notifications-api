#!/bin/bash

set -e

source environment.sh
celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=1 --autoreload -Q sms