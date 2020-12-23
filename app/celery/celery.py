import time
from gds_metrics.metrics import Histogram
from celery import Celery, Task
from celery.signals import worker_process_shutdown
from flask import g, request
from flask.ctx import has_request_context, has_app_context


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
    SQS_APPLY_ASYNC_DURATION_SECONDS = Histogram(
        'sqs_apply_async_duration_seconds',
        'Time taken to put task on queue',
        ['task_name']
    )

    class NotifyTask(Task):
        abstract = True
        start = None

        def on_success(self, retval, task_id, args, kwargs):
            elapsed_time = time.time() - self.start
            app.logger.info(
                "{task_name} took {time}".format(
                    task_name=self.name, time="{0:.4f}".format(elapsed_time)
                )
            )

        def on_failure(self, exc, task_id, args, kwargs, einfo):
            # ensure task will log exceptions to correct handlers
            app.logger.exception('Celery task: {} failed'.format(self.name))
            super().on_failure(exc, task_id, args, kwargs, einfo)

        def __call__(self, *args, **kwargs):
            # ensure task has flask context to access config, logger, etc
            with app.app_context():
                self.start = time.time()
                # Remove 'request_id' from the kwargs (so the task doesn't get an unexpected kwarg), then add it to g
                # so that it gets logged
                g.request_id = kwargs.pop('request_id', None)
                return super().__call__(*args, **kwargs)

        def apply_async(self, args=None, kwargs=None, task_id=None, producer=None,
                        link=None, link_error=None, **options):
            kwargs = kwargs or {}
            if has_request_context() and hasattr(request, 'request_id'):
                kwargs['request_id'] = request.request_id
            elif has_app_context() and 'request_id' in g:
                kwargs['request_id'] = g.request_id

            with SQS_APPLY_ASYNC_DURATION_SECONDS.labels(self.name).time():
                return super().apply_async(args, kwargs, task_id, producer, link, link_error, **options)

    return NotifyTask


class NotifyCelery(Celery):

    def init_app(self, app):
        super().__init__(
            app.import_name,
            broker=app.config['BROKER_URL'],
            task_cls=make_task(app),
        )

        self.conf.update(app.config)
        self._app = app
