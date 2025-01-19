import os

from gds_metrics.gunicorn import child_exit  # noqa
from notifications_utils.gunicorn_defaults import set_gunicorn_defaults

set_gunicorn_defaults(globals())


workers = 4
worker_class = "eventlet"
worker_connections = 256
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
keepalive = 90
timeout = int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30))  # though has little effect with eventlet worker_class

debug_post_threshold = os.getenv("NOTIFY_GUNICORN_DEBUG_POST_REQUEST_LOG_THRESHOLD_SECONDS", None)
if debug_post_threshold:
    debug_post_threshold_float = float(debug_post_threshold)

    def pre_request(worker, req):
        # using os.times() to avoid additional imports before eventlet monkeypatching
        req._pre_request_elapsed = os.times().elapsed

    def _tuples_to_lists(value):
        if isinstance(value, tuple):
            # convert to list for more compact (and json-able) representation
            return list(value)

        return value

    def post_request(worker, req, environ, resp):
        elapsed = os.times().elapsed - req._pre_request_elapsed
        if elapsed > debug_post_threshold_float:
            import json
            import time

            import psutil

            # consume this iterator to give cpu_percent calculation a "start time" to work with
            list(psutil.process_iter(["cpu_percent"]))
            time.sleep(0.1)  # period over which to calculate cpu_percent

            attrs = ["pid", "name", "cpu_percent", "status", "memory_info"]

            context = {
                "request_time": elapsed,
                "processes": json.dumps(
                    [
                        attrs,
                        [[_tuples_to_lists(p.info[a]) for a in attrs] for p in psutil.process_iter(attrs)],
                    ]
                ),
            }
            worker.log.info(
                "post-request diagnostics for request of %(request_time)ss",
                context,
                extra=context,
            )
