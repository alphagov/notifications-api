#!/bin/bash
case $NOTIFY_APP_NAME in
  api)
    unset GUNICORN_CMD_ARGS
    exec scripts/run_app_paas.sh gunicorn -c /home/vcap/app/gunicorn_config.py application
    ;;
  delivery-worker-ecs-fixup)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q broadcast-tasks,create-letters-pdf-tasks,database-tasks,job-tasks,letter-tasks,notify-internal-tasks,periodic-tasks,reporting-tasks,research-mode-tasks,retry-tasks,save-api-email-tasks,save-api-sms-tasks,send-email-tasks,send-letter-tasks,send-sms-tasks,service-callbacks,service-callbacks-retry,ses-callbacks,sms-callbacks
    ;;
  delivery-worker-retry-tasks)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q retry-tasks
    ;;
  delivery-worker-letters)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q create-letters-pdf-tasks,letter-tasks
    ;;
  delivery-worker-jobs)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q database-tasks,job-tasks
    ;;
  delivery-worker-research)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q research-mode-tasks
    ;;
  delivery-worker-sender)
    exec scripts/run_multi_worker_app_paas.sh celery multi start 3 -c 4 -A run_celery.notify_celery --loglevel=INFO \
    --logfile=/dev/null --pidfile=/tmp/celery%N.pid -Q send-sms-tasks,send-email-tasks
    ;;
  delivery-worker-sender-letters)
    # at the default of 2 instances with 4 concurrent workers, we hit DVLA's 50rps rate limit 
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=3 \
    -Q send-letter-tasks
    ;;
  delivery-worker-periodic)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=2 \
    -Q periodic-tasks
    ;;
  delivery-worker-reporting)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q reporting-tasks
    ;;
  # Only consume the notify-internal-tasks queue on this app so that Notify messages are processed as a priority
  delivery-worker-internal)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q notify-internal-tasks
    ;;
  delivery-worker-broadcasts)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=2 \
    -Q broadcast-tasks
    ;;
  delivery-worker-receipts)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q ses-callbacks,sms-callbacks
    ;;
  delivery-worker-service-callbacks)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q service-callbacks,service-callbacks-retry
    ;;
  delivery-worker-save-api-notifications)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery worker --loglevel=INFO --concurrency=4 \
    -Q save-api-email-tasks,save-api-sms-tasks
    ;;
  delivery-celery-beat)
    exec scripts/run_app_paas.sh celery -A run_celery.notify_celery beat --loglevel=INFO
    ;;
  *)
    echo "Unknown notify_app_name $NOTIFY_APP_NAME"
    exit 1
    ;;
esac
