import os
import sys
import traceback
import gunicorn
import eventlet
import socket

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
    for _threadId, stack in sys._current_frames().items():
        worker.log.error(''.join(traceback.format_stack(stack)))


def on_exit(server):
    server.log.info("Stopping Notifications API")


def worker_int(worker):
    worker.log.info("worker: received SIGINT {}".format(worker.pid))


def fix_ssl_monkeypatching():
    """
    eventlet works by monkey-patching core IO libraries (such as ssl) to be non-blocking. However, there's currently
    a bug: In the normal socket library it may throw a timeout error as a `socket.timeout` exception. However
    eventlet.green.ssl's patch raises an ssl.SSLError('timed out',) instead. redispy handles socket.timeout but not
    ssl.SSLError, so we solve this by monkey patching the monkey patching code to raise the correct exception type
    :scream:

    https://github.com/eventlet/eventlet/issues/692
    """
    # this has probably already been called somewhere in gunicorn internals, however, to be sure, we invoke it again.
    # eventlet.monkey_patch can be called multiple times without issue
    eventlet.monkey_patch()
    eventlet.green.ssl.timeout_exc = socket.timeout


fix_ssl_monkeypatching()
