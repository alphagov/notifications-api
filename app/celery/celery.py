from datetime import timedelta

from app.celery import QueueNames
from celery import Celery
from celery.schedules import crontab
from kombu import Queue, Exchange
from app.definitions import (
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE
)


class CeleryConfig:
    def __init__(self, config):
        self.broker_transport_options['queue_name_prefix'] = config['NOTIFICATION_QUEUE_PREFIX']

    broker_url = 'sqs://'
    broker_transport_options = {
        'region': 'sqs.eu-west-1',
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 310,
        'queue_name_prefix': None
    }
    enable_utc = True,
    timezone = 'Europe/London'
    accept_content = ['json']
    task_serializer = 'json'
    imports = ('app.celery.tasks', 'app.celery.scheduled_tasks')
    beat_schedule = {
        'run-scheduled-jobs': {
            'task': 'run-scheduled-jobs',
            'schedule': crontab(minute=1),
            'options': {'queue': QueueNames.PERIODIC}
        },
        # 'send-scheduled-notifications': {
        #     'task': 'send-scheduled-notifications',
        #     'schedule': crontab(minute='*/15'),
        #     'options': {'queue': 'periodic'}
        # },
        'delete-verify-codes': {
            'task': 'delete-verify-codes',
            'schedule': timedelta(minutes=63),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-invitations': {
            'task': 'delete-invitations',
            'schedule': timedelta(minutes=66),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-sms-notifications': {
            'task': 'delete-sms-notifications',
            'schedule': crontab(minute=0, hour=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-email-notifications': {
            'task': 'delete-email-notifications',
            'schedule': crontab(minute=20, hour=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-letter-notifications': {
            'task': 'delete-letter-notifications',
            'schedule': crontab(minute=40, hour=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-inbound-sms': {
            'task': 'delete-inbound-sms',
            'schedule': crontab(minute=0, hour=1),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'send-daily-performance-platform-stats': {
            'task': 'send-daily-performance-platform-stats',
            'schedule': crontab(minute=0, hour=2),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'switch-current-sms-provider-on-slow-delivery': {
            'task': 'switch-current-sms-provider-on-slow-delivery',
            'schedule': crontab(),  # Every minute
            'options': {'queue': QueueNames.PERIODIC}
        },
        'timeout-sending-notifications': {
            'task': 'timeout-sending-notifications',
            'schedule': crontab(minute=0, hour=3),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'remove_sms_email_jobs': {
            'task': 'remove_csv_files',
            'schedule': crontab(minute=0, hour=4),
            'options': {'queue': QueueNames.PERIODIC},
            'kwargs': {'job_types': [EMAIL_TYPE, SMS_TYPE]}
        },
        'remove_letter_jobs': {
            'task': 'remove_csv_files',
            'schedule': crontab(minute=20, hour=4),
            'options': {'queue': QueueNames.PERIODIC},
            'kwargs': {'job_types': [LETTER_TYPE]}
        },
        'timeout-job-statistics': {
            'task': 'timeout-job-statistics',
            'schedule': crontab(minute=0, hour=5),
            'options': {'queue': QueueNames.PERIODIC}
        }
    }
    task_queues = []


class NotifyCelery(Celery):
    def init_app(self, app):
        super().__init__(app.import_name, broker=CeleryConfig.broker_url)

        if app.config['INITIALISE_QUEUES']:
            for queue in QueueNames.all_queues():
                CeleryConfig.task_queues.append(
                    Queue(queue, Exchange('default'), routing_key=queue)
                )

        self.config_from_object(CeleryConfig(app.config))
        TaskBase = self.Task

        class ContextTask(TaskBase):
            abstract = True

            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return TaskBase.__call__(self, *args, **kwargs)

        self.Task = ContextTask
