import os

from notifications_utils.gunicorn.defaults import set_gunicorn_defaults

set_gunicorn_defaults(globals())


# importing child_exit from gds_metrics.gunicorn has the side effect of eagerly importing
# prometheus_client, flask, werkzeug and more, which is a bad idea to do before eventlet/gevent
# has done its monkeypatching. use a nested import for the rare cases child_exit is actually
# called instead.
def child_exit(server, worker):
    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(worker.pid)


workers = 2
worker_class = "eventlet"
worker_connections = 256
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
keepalive = 32  # disable temporarily for diagnosing issues
timeout = int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30))  # though has little effect with eventlet/gevent worker_class

debug_post_threshold_seconds = os.getenv("NOTIFY_GUNICORN_DEBUG_POST_REQUEST_DUMP_THRESHOLD_SECONDS", None)
debug_post_threshold_concurrency = os.getenv("NOTIFY_GUNICORN_DEBUG_POST_REQUEST_DUMP_THRESHOLD_CONCURRENCY", "0")
debug_post_backoff_seconds = os.getenv("NOTIFY_GUNICORN_DEBUG_POST_REQUEST_DUMP_BACKOFF_SECONDS", "1")

if debug_post_threshold_seconds:
    debug_post_threshold_seconds_float = float(debug_post_threshold_seconds)
    debug_post_threshold_concurrency_int = int(debug_post_threshold_concurrency)
    debug_post_backoff_seconds_float = float(debug_post_backoff_seconds)

    last_dumped = 0
    concurrent_requests = 0

    def pre_request(worker, req):
        global concurrent_requests
        concurrent_requests += 1
        # using os.times() to avoid additional imports before eventlet monkeypatching
        req._pre_request_elapsed = os.times().elapsed

    def post_request(worker, req, environ, resp):
        global concurrent_requests
        global last_dumped
        concurrent_requests -= 1

        if worker_class == "gevent":
            from datetime import datetime
            from gevent.util import print_run_info

        now_elapsed = os.times().elapsed
        elapsed = now_elapsed - req._pre_request_elapsed
        if (
            elapsed > debug_post_threshold_seconds_float
            and concurrent_requests > debug_post_threshold_concurrency_int
            and last_dumped + debug_post_backoff_seconds_float < now_elapsed
        ):
            last_dumped = now_elapsed
            if worker_class == "gevent":
                timestamp = datetime.utcnow().isoformat(timespec="microseconds")
                p = f"/tmp/dump.{timestamp}"
                with open(p, "w") as f:
                    print_run_info(file=f)

                worker.log.info("Wrote dump %s", p)
