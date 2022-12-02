#!/usr/bin/env python

# import prometheus before any other code. If gds_metrics is imported first it will write a prometheus file to disk
# that will never be read from (since we don't have prometheus celery stats). If prometheus is imported first,
# prometheus will simply store the metrics in memory
import prometheus_client  # noqa

# notify_celery is referenced from manifest_delivery_base.yml, and cannot be removed
from app import create_app, notify_celery  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("delivery")
create_app(application)
application.app_context().push()
