import os

from notifications_utils.gunicorn.defaults import set_gunicorn_defaults

set_gunicorn_defaults(globals())


workers = int(os.getenv("GUNICORN_WORKERS", "4"))
worker_class = "notifications_utils.gunicorn.eventlet.OtelAwareEventletWorker"
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "8"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "0"))
timeout = int(os.getenv("HTTP_SERVE_TIMEOUT_SECONDS", 30))  # though has little effect with eventlet worker_class
