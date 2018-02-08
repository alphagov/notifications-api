import time

from flask import current_app
from celery import Celery, Task


class NotifyTask(Task):
    abstract = True
    start = None

    def on_success(self, retval, task_id, args, kwargs):
        elapsed_time = time.time() - self.start
        current_app.logger.info(
            "{task_name} took {time}".format(
                task_name=self.name, time="{0:.4f}".format(elapsed_time)
            )
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # ensure task will log exceptions to correct handlers
        current_app.logger.exception('Celery task failed')
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def __call__(self, *args, **kwargs):
        # ensure task has flask context to access config, logger, etc
        with current_app.app_context():
            self.start = time.time()
            return super().__call__(*args, **kwargs)


class NotifyCelery(Celery):

    def init_app(self, app):
        super().__init__(
            app.import_name,
            broker=app.config['BROKER_URL'],
            task_cls=NotifyTask,
        )

        self.conf.update(app.config)
