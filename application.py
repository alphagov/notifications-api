##!/usr/bin/env python
import os

import notifications_utils.greenlet as utils_greenlet

if utils_greenlet.using_gevent:
    from psycogreen.gevent import patch_psycopg

    # eventlet does this automatically, but gevent doesn't
    patch_psycopg()

from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

application = NotifyApiFlaskApp("app")

create_app(application)

if utils_greenlet.using_eventlet or utils_greenlet.using_gevent:
    http_serve_timeout_seconds = int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30))
    application.wsgi_app = utils_greenlet.RequestHandlingTimeoutMiddleware(  # type: ignore[method-assign]
        application.wsgi_app,
        timeout_seconds=http_serve_timeout_seconds,
        soft_timeout_seconds=http_serve_timeout_seconds - 0.5,
    )

    if application.config["NOTIFY_GREENLET_STATS"]:
        import greenlet

        greenlet.settrace(utils_greenlet.account_greenlet_times)
        application._server_greenlet = greenlet.getcurrent()  # type: ignore[attr-defined]
