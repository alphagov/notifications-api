import os

from gds_metrics.gunicorn import child_exit  # noqa
from notifications_utils.gunicorn_defaults import set_gunicorn_defaults

set_gunicorn_defaults(globals())


workers = 4
worker_class = "eventlet"
worker_connections = 256
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
keepalive = 90
