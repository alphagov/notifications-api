#!/bin/bash

set -e

source environment.sh
celery -A run_celery.notify_celery worker --loglevel=INFO --logfile=/var/log/notify/application.log --concurrency=4 -Q sms,sms_code,email_code