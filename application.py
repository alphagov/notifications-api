##!/usr/bin/env python
import os

from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

from notifications_utils.eventlet import EventletTimeoutMiddleware, using_eventlet  # noqa

application = NotifyApiFlaskApp("app")

create_app(application)

if using_eventlet:
    application.wsgi_app = EventletTimeoutMiddleware(
        application.wsgi_app,
        timeout_seconds=int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30)),
    )
