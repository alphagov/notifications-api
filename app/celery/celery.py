from flask import current_app
from celery import Celery, Task


class NotifyTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        # ensure task will log exceptions to correct handlers
        current_app.logger.exception('Celery task failed')
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def __call__(self, *args, **kwargs):
        # ensure task has flask context to access config, logger, etc
        with current_app.app_context():
            return super().__call__(*args, **kwargs)


class NotifyCelery(Celery):

    def init_app(self, app):
        super().__init__(
            app.import_name,
            broker=app.config['BROKER_URL'],
            task_cls=NotifyTask,
        )

        self.conf.update(app.config)
