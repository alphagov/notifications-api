import os
import sys
import traceback
import gunicorn

from gds_metrics.gunicorn import child_exit  # noqa

workers = 4
worker_class = "eventlet"
worker_connections = 256
errorlog = "/home/vcap/logs/gunicorn_error.log"
bind = "0.0.0.0:{}".format(os.getenv("PORT"))
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
gunicorn.SERVER_SOFTWARE = 'None'


def on_starting(server):
    server.log.info("Starting Notifications API")


def worker_abort(worker):
    worker.log.info("worker received ABORT {}".format(worker.pid))
    for threadId, stack in sys._current_frames().items():
        worker.log.error(''.join(traceback.format_stack(stack)))


def on_exit(server):
    server.log.info("Stopping Notifications API")


def worker_int(worker):
    worker.log.info("worker: received SIGINT {}".format(worker.pid))
