##!/usr/bin/env python
from app.performance import init_performance_monitoring

init_performance_monitoring()

from app import create_app  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp  # noqa

application = NotifyApiFlaskApp("app")

import sys

using_eventlet = False
if "eventlet" in sys.modules:
    try:
        import socket
        from eventlet.patcher import is_monkey_patched
    except ImportError:
        pass
    else:
        if is_monkey_patched(socket):
            using_eventlet = True

create_app(application)

if using_eventlet:
    from eventlet.timeout import Timeout
    class EventletTimeoutMiddleware:
        def __init__(self, app, timeout_seconds=30):
            self._app = app
            self._timeout_seconds = timeout_seconds

        def __call__(self, *args, **kwargs):
            with Timeout(self._timeout_seconds):
                return self._app(*args, **kwargs)

    application = EventletTimeoutMiddleware(application)
