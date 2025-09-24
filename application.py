##!/usr/bin/env python
import os

from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

import notifications_utils.eventlet as utils_eventlet  # noqa

application = NotifyApiFlaskApp("app")

create_app(application)

from collections.abc import Callable
class DropRequestsMiddleware:
    _app: Callable

    def __init__(self, app: Callable):
        self._app = app

    def __call__(self, *args, **kwargs):
        import random
        if random.uniform(0, 1) <= float(os.getenv("REQUEST_SUCCESS_PROBABILITY", "1")):
            return self._app(*args, **kwargs)
        else:
            raise Exception("kaboom")

application.wsgi_app = DropRequestsMiddleware(application.wsgi_app)

if utils_eventlet.using_eventlet:
    application.wsgi_app = utils_eventlet.EventletTimeoutMiddleware(
        application.wsgi_app,
        timeout_seconds=int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30)),
    )

    if application.config["NOTIFY_EVENTLET_STATS"]:
        import greenlet

        greenlet.settrace(utils_eventlet.account_greenlet_times)
        application._server_greenlet = greenlet.getcurrent()
