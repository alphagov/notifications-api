##!/usr/bin/env python
import os

from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

import notifications_utils.greenlet as utils_greenlet  # noqa

application = NotifyApiFlaskApp("app")

create_app(application)

if utils_greenlet.using_eventlet or utils_greenlet.using_gevent:
    application.wsgi_app = utils_greenlet.RequestHandlingTimeoutMiddleware(
        application.wsgi_app,
        timeout_seconds=int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30)),
    )

    if application.config["NOTIFY_GREENLET_STATS"]:
        import greenlet

        greenlet.settrace(utils_greenlet.account_greenlet_times)
        application._server_greenlet = greenlet.getcurrent()
