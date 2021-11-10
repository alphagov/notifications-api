import time

from celery import Celery, Task
from celery.signals import worker_process_shutdown
from flask import g, request
from flask.ctx import has_app_context, has_request_context


@worker_process_shutdown.connect
def log_on_worker_shutdown(sender, signal, pid, exitcode, **kwargs):
    # imported here to avoid circular imports
    from app import notify_celery

    # if the worker has already restarted at least once, then we no longer have app context and current_app won't work
    # to create a new one. Instead we have to create a new app context from the original flask app and use that instead.
    with notify_celery._app.app_context():
        # if the worker has restarted
        notify_celery._app.logger.info('worker shutdown: PID: {} Exitcode: {}'.format(pid, exitcode))


def make_task(app):
    class NotifyTask(Task):
        abstract = True
        start = None
        typing = False

        def on_success(self, retval, task_id, args, kwargs):
            elapsed_time = time.monotonic() - self.start
            delivery_info = self.request.delivery_info or {}
            queue_name = delivery_info.get('routing_key', 'none')

            app.logger.info(
                "Celery task {task_name} (queue: {queue_name}) took {time}".format(
                    task_name=self.name,
                    queue_name=queue_name,
                    time="{0:.4f}".format(elapsed_time)
                )
            )

            app.statsd_client.timing(
                "celery.{queue_name}.{task_name}.success".format(
                    task_name=self.name,
                    queue_name=queue_name
                ), elapsed_time
            )

        def on_failure(self, exc, task_id, args, kwargs, einfo):
            delivery_info = self.request.delivery_info or {}
            queue_name = delivery_info.get('routing_key', 'none')

            app.logger.exception(
                "Celery task {task_name} (queue: {queue_name}) failed".format(
                    task_name=self.name,
                    queue_name=queue_name,
                )
            )

            app.statsd_client.incr(
                "celery.{queue_name}.{task_name}.failure".format(
                    task_name=self.name,
                    queue_name=queue_name
                )
            )

            super().on_failure(exc, task_id, args, kwargs, einfo)

        def __call__(self, *args, **kwargs):
            # ensure task has flask context to access config, logger, etc
            with app.app_context():
                self.start = time.monotonic()
                # TEMPORARY: remove old piggyback values from kwargs
                kwargs.pop('request_id', None)
                # Add 'request_id' to 'g' so that it gets logged. Note
                # that each header is a direct attribute of the task
                # context (aka "request").
                g.request_id = self.request.get('notify_request_id')

                return super().__call__(*args, **kwargs)

    return NotifyTask


class NotifyCelery(Celery):

    def init_app(self, app):
        super().__init__(
            app.import_name,
            broker=app.config['CELERY']['broker_url'],
            task_cls=make_task(app),
        )

        self.conf.update(app.config['CELERY'])
        self._app = app

    def send_task(self, name, args=None, kwargs=None, **other_kwargs):
        other_kwargs['headers'] = other_kwargs.get('headers') or {}

        if has_request_context() and hasattr(request, 'request_id'):
            other_kwargs['headers']['notify_request_id'] = request.request_id
        elif has_app_context() and 'request_id' in g:
            other_kwargs['headers']['notify_request_id'] = g.request_id

        return super().send_task(name, args, kwargs, **other_kwargs)
