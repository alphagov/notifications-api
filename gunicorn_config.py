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


workers = 1
worker_class = "gevent"
worker_connections = 256
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
keepalive = 32  # disable temporarily for diagnosing issues
timeout = int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30))  # though has little effect with gevent worker_class
