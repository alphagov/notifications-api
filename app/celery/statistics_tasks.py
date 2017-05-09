from app import notify_celery
from app.statsd_decorators import statsd


@notify_celery.task(bind=True, name='record_initial_job_statistics')
@statsd(namespace="tasks")
def record_initial_job_statistics(notification):
    pass

