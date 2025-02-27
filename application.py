##!/usr/bin/env python
import os
from app.profiler_notify import ProfilerMiddleware
from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

import notifications_utils.eventlet as utils_eventlet  # noqa

application = NotifyApiFlaskApp("app")

create_app(application)

profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "profiler")
os.makedirs(profile_dir, exist_ok=True)

application.wsgi_app = ProfilerMiddleware(
            application.wsgi_app,
            profile_dir=profile_dir,
            filename_format="{method}-{path}-{time:.0f}-{elapsed:.0f}ms.prof",
        )

if utils_eventlet.using_eventlet:
    application.wsgi_app = utils_eventlet.EventletTimeoutMiddleware(
        application.wsgi_app,
        timeout_seconds=int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30)),
    )

    if application.config["NOTIFY_EVENTLET_STATS"]:
        import greenlet

        greenlet.settrace(utils_eventlet.account_greenlet_times)
        application._server_greenlet = greenlet.getcurrent()
