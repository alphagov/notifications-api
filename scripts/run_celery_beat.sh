#!/bin/bash

set -e

source environment.sh
celery -A run_celery.notify_celery beat --loglevel=INFO
