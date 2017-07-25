from celery import Celery


class NotifyCelery(Celery):

    def init_app(self, app):
        super().__init__(app.import_name, broker=app.config['BROKER_URL'])
        self.conf.update(app.config)
        TaskBase = self.Task

        class ContextTask(TaskBase):
            abstract = True

            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return TaskBase.__call__(self, *args, **kwargs)
        self.Task = ContextTask
