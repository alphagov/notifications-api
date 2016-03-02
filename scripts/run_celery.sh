#!/bin/bash

set -e

source environment.sh
celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 -Q sms,sms-code,email-code,email,process-job,bulk-sms,bulk-email,email-invited-user
