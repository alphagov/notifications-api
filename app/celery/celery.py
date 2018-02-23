import time

from celery import Celery, Task


def make_task(app):
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
                return super().__call__(*args, **kwargs)

    return NotifyTask


class NotifyCelery(Celery):

    def init_app(self, app):
        super().__init__(
            app.import_name,
            broker=app.config['BROKER_URL'],
            task_cls=make_task(app),
        )

        self.conf.update(app.config)
