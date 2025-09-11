#!/usr/bin/env python

import notifications_utils.logging.celery as celery_logging

from app.performance import init_performance_monitoring

init_performance_monitoring()

# import prometheus before any other code. If gds_metrics is imported first it will write a prometheus file to disk
# that will never be read from (since we don't have prometheus celery stats). If prometheus is imported first,
# prometheus will simply store the metrics in memory
import prometheus_client  # noqa

# notify_celery is referenced from manifest_delivery_base.yml, and cannot be removed
from app import create_app, notify_celery  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

application = NotifyApiFlaskApp("delivery")
create_app(application)
celery_logging.set_up_logging(application.config)
application.app_context().push()
