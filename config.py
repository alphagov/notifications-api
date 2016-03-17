from datetime import timedelta
from kombu import Exchange, Queue
import os


class Config(object):
    DEBUG = False
    ADMIN_BASE_URL = os.environ['ADMIN_BASE_URL']
    ADMIN_CLIENT_USER_NAME = os.environ['ADMIN_CLIENT_USER_NAME']
    ADMIN_CLIENT_SECRET = os.environ['ADMIN_CLIENT_SECRET']
    AWS_REGION = os.environ['AWS_REGION']
    DANGEROUS_SALT = os.environ['DANGEROUS_SALT']
    INVITATION_EXPIRATION_DAYS = int(os.environ['INVITATION_EXPIRATION_DAYS'])
    INVITATION_EMAIL_FROM = os.environ['INVITATION_EMAIL_FROM']
    NOTIFY_APP_NAME = 'api'
    NOTIFY_LOG_PATH = '/var/log/notify/application.log'
    NOTIFY_JOB_QUEUE = os.environ['NOTIFY_JOB_QUEUE']
    # Notification Queue names are a combination of a prefx plus a name
    NOTIFICATION_QUEUE_PREFIX = os.environ['NOTIFICATION_QUEUE_PREFIX']
    SECRET_KEY = os.environ['SECRET_KEY']
    SQLALCHEMY_COMMIT_ON_TEARDOWN = False
    SQLALCHEMY_DATABASE_URI = os.environ['SQLALCHEMY_DATABASE_URI']
    SQLALCHEMY_RECORD_QUERIES = True
    VERIFY_CODE_FROM_EMAIL_ADDRESS = os.environ['VERIFY_CODE_FROM_EMAIL_ADDRESS']
    NOTIFY_EMAIL_DOMAIN = os.environ['NOTIFY_EMAIL_DOMAIN']
    PAGE_SIZE = 50

    BROKER_URL = 'sqs://'
    BROKER_TRANSPORT_OPTIONS = {
        'region': 'eu-west-1',
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 60,  # 60 seconds
        'queue_name_prefix': os.environ['NOTIFICATION_QUEUE_PREFIX'] + '-'
    }
    CELERY_ENABLE_UTC = True,
    CELERY_TIMEZONE = 'Europe/London'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_IMPORTS = ('app.celery.tasks',)
    CELERYBEAT_SCHEDULE = {
        'delete-verify-codes': {
            'task': 'delete-verify-codes',
            'schedule': timedelta(minutes=63),
            'options': {'queue': 'periodic'}
        },
        'delete-invitations': {
            'task': 'delete-invitations',
            'schedule': timedelta(minutes=66),
            'options': {'queue': 'periodic'}
        },
        'delete-failed-notifications': {
            'task': 'delete-failed-notifications',
            'schedule': timedelta(minutes=60),
            'options': {'queue': 'periodic'}
        },
        'delete-successful-notifications': {
            'task': 'delete-successful-notifications',
            'schedule': timedelta(minutes=31),
            'options': {'queue': 'periodic'}
        }
    }
    CELERY_QUEUES = [
        Queue('periodic', Exchange('default'), routing_key='periodic'),
        Queue('sms', Exchange('default'), routing_key='sms'),
        Queue('email', Exchange('default'), routing_key='email'),
        Queue('sms-code', Exchange('default'), routing_key='sms-code'),
        Queue('email-code', Exchange('default'), routing_key='email-code'),
        Queue('email-reset-password', Exchange('default'), routing_key='email-reset-password'),
        Queue('process-job', Exchange('default'), routing_key='process-job'),
        Queue('bulk-sms', Exchange('default'), routing_key='bulk-sms'),
        Queue('bulk-email', Exchange('default'), routing_key='bulk-email'),
        Queue('email-invited-user', Exchange('default'), routing_key='email-invited-user')
    ]
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_NUMBER = os.getenv('TWILIO_NUMBER')
    FIRETEXT_NUMBER = os.getenv('FIRETEXT_NUMBER')
    FIRETEXT_API_KEY = os.getenv("FIRETEXT_API_KEY")


class Development(Config):
    DEBUG = True


class Test(Development):
    pass

configs = {
    'live': 'config_live.Live',
    'staging': 'config_staging.Staging',
    'preview': 'config.Config'
}
