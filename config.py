from datetime import timedelta
from celery.schedules import crontab
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
    # Notification Queue names are a combination of a prefix plus a name
    NOTIFICATION_QUEUE_PREFIX = os.environ['NOTIFICATION_QUEUE_PREFIX']
    SECRET_KEY = os.environ['SECRET_KEY']
    SQLALCHEMY_COMMIT_ON_TEARDOWN = False
    SQLALCHEMY_DATABASE_URI = os.environ['SQLALCHEMY_DATABASE_URI']
    SQLALCHEMY_RECORD_QUERIES = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    VERIFY_CODE_FROM_EMAIL_ADDRESS = os.environ['VERIFY_CODE_FROM_EMAIL_ADDRESS']
    NOTIFY_EMAIL_DOMAIN = os.environ['NOTIFY_EMAIL_DOMAIN']
    PAGE_SIZE = 50
    SMS_CHAR_COUNT_LIMIT = 495
    MMG_URL = os.environ['MMG_URL']

    NOTIFY_SERVICE_ID = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
    INVITATION_EMAIL_TEMPLATE_ID = '4f46df42-f795-4cc4-83bb-65ca312f49cc'
    SMS_CODE_TEMPLATE_ID = '36fb0730-6259-4da1-8a80-c8de22ad4246'
    EMAIL_VERIFY_CODE_TEMPLATE_ID = 'ece42649-22a8-4d06-b87f-d52d5d3f0a27'
    PASSWORD_RESET_TEMPLATE_ID = '474e9242-823b-4f99-813d-ed392e7f1201'
    ALREADY_REGISTERED_EMAIL_TEMPLATE_ID = '0880fbb1-a0c6-46f0-9a8e-36c986381ceb'

    BROKER_URL = 'sqs://'
    BROKER_TRANSPORT_OPTIONS = {
        'region': 'eu-west-1',
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 14410,  # 4 hours 10 seconds. 10 seconds longer than max retry
        'queue_name_prefix': os.environ['NOTIFICATION_QUEUE_PREFIX'] + '-'
    }
    CELERY_ENABLE_UTC = True,
    CELERY_TIMEZONE = 'Europe/London'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_IMPORTS = ('app.celery.tasks', 'app.celery.scheduled_tasks')
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
            'schedule': crontab(minute=0, hour='0,1,2'),
            'options': {'queue': 'periodic'}
        },
        'delete-successful-notifications': {
            'task': 'delete-successful-notifications',
            'schedule': crontab(minute=0, hour='0,1,2'),
            'options': {'queue': 'periodic'}
        },
        'timeout-sending-notifications': {
            'task': 'timeout-sending-notifications',
            'schedule': crontab(minute=0, hour='0,1,2'),
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
        Queue('remove-job', Exchange('default'), routing_key='remove-job'),
        Queue('bulk-sms', Exchange('default'), routing_key='bulk-sms'),
        Queue('bulk-email', Exchange('default'), routing_key='bulk-email'),
        Queue('email-invited-user', Exchange('default'), routing_key='email-invited-user'),
        Queue('email-registration-verification', Exchange('default'), routing_key='email-registration-verification'),
        Queue('research-mode', Exchange('default'), routing_key='research-mode'),
        Queue('retry', Exchange('default'), routing_key='retry'),
        Queue('email-already-registered', Exchange('default'), routing_key='email-already-registered')
    ]
    FIRETEXT_API_KEY = os.getenv("FIRETEXT_API_KEY")
    LOADTESTING_NUMBER = os.getenv('LOADTESTING_NUMBER')
    LOADTESTING_API_KEY = os.getenv("LOADTESTING_API_KEY")
    CSV_UPLOAD_BUCKET_NAME = 'local-notifications-csv-upload'
    NOTIFICATIONS_ALERT = 5  # five mins
    FROM_NUMBER = os.getenv('FROM_NUMBER')

    STATSD_ENABLED = False
    STATSD_HOST = "localhost"
    STATSD_PORT = None
    STATSD_PREFIX = None

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200


class Development(Config):
    DEBUG = True
    API_HOST_NAME = os.environ['API_HOST_NAME']
    MMG_API_KEY = os.environ['MMG_API_KEY']
    CSV_UPLOAD_BUCKET_NAME = 'development-notifications-csv-upload'


class Preview(Config):
    MMG_API_KEY = os.environ['MMG_API_KEY']
    API_HOST_NAME = os.environ['API_HOST_NAME']
    CSV_UPLOAD_BUCKET_NAME = 'preview-notifications-csv-upload'


class Test(Development):
    MMG_API_KEY = os.environ['MMG_API_KEY']
    API_HOST_NAME = os.environ['API_HOST_NAME']
    CSV_UPLOAD_BUCKET_NAME = 'test-notifications-csv-upload'


configs = {
    'development': 'config.Development',
    'test': 'config.Test',
    'live': 'config_live.Live',
    'staging': 'config_staging.Staging',
    'preview': 'config.Preview'
}
