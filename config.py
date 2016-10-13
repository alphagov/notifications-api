from datetime import timedelta
from celery.schedules import crontab
from kombu import Exchange, Queue
import os


class Config(object):
    ########################################
    # Secrets that are held in credstash ###
    ########################################

    # URL of admin app
    ADMIN_BASE_URL = os.environ['ADMIN_BASE_URL']

    # admin app api key
    ADMIN_CLIENT_SECRET = os.environ['ADMIN_CLIENT_SECRET']

    # encyption secret/salt
    SECRET_KEY = os.environ['SECRET_KEY']
    DANGEROUS_SALT = os.environ['DANGEROUS_SALT']

    # DB conection string
    SQLALCHEMY_DATABASE_URI = os.environ['SQLALCHEMY_DATABASE_URI']

    # MMG API Url
    MMG_URL = os.environ['MMG_URL']

    # MMG API Key
    MMG_API_KEY = os.environ['MMG_API_KEY']

    # Firetext API Key
    FIRETEXT_API_KEY = os.getenv("FIRETEXT_API_KEY")

    # Firetext simluation key
    LOADTESTING_API_KEY = os.getenv("LOADTESTING_API_KEY")

    # Hosted graphite statsd prefix
    STATSD_PREFIX = os.getenv('STATSD_PREFIX')

    # Prefix to identify queues in SQS
    NOTIFICATION_QUEUE_PREFIX = os.getenv('NOTIFICATION_QUEUE_PREFIX')

    ###########################
    # Default config values ###
    ###########################

    DEBUG = False
    NOTIFY_ENVIRONMENT = 'development'
    ADMIN_CLIENT_USER_NAME = 'notify-admin'
    AWS_REGION = 'eu-west-1'
    INVITATION_EXPIRATION_DAYS = 2
    NOTIFY_APP_NAME = 'api'
    NOTIFY_LOG_PATH = '/var/log/notify/application.log'
    SQLALCHEMY_COMMIT_ON_TEARDOWN = False
    SQLALCHEMY_RECORD_QUERIES = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    PAGE_SIZE = 50
    SMS_CHAR_COUNT_LIMIT = 495
    BRANDING_PATH = '/static/images/email-template/crests/'
    TEST_MESSAGE_FILENAME = 'Test message'

    NOTIFY_SERVICE_ID = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
    INVITATION_EMAIL_TEMPLATE_ID = '4f46df42-f795-4cc4-83bb-65ca312f49cc'
    SMS_CODE_TEMPLATE_ID = '36fb0730-6259-4da1-8a80-c8de22ad4246'
    EMAIL_VERIFY_CODE_TEMPLATE_ID = 'ece42649-22a8-4d06-b87f-d52d5d3f0a27'
    PASSWORD_RESET_TEMPLATE_ID = '474e9242-823b-4f99-813d-ed392e7f1201'
    ALREADY_REGISTERED_EMAIL_TEMPLATE_ID = '0880fbb1-a0c6-46f0-9a8e-36c986381ceb'
    CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID = 'eb4d9930-87ab-4aef-9bce-786762687884'

    BROKER_URL = 'sqs://'
    BROKER_TRANSPORT_OPTIONS = {
        'region': AWS_REGION,
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 14410,  # 4 hours 10 seconds. 10 seconds longer than max retry
        'queue_name_prefix': NOTIFICATION_QUEUE_PREFIX
    }
    CELERY_ENABLE_UTC = True,
    CELERY_TIMEZONE = 'Europe/London'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_IMPORTS = ('app.celery.tasks', 'app.celery.scheduled_tasks')
    CELERYBEAT_SCHEDULE = {
        'run-scheduled-jobs': {
            'task': 'run-scheduled-jobs',
            'schedule': crontab(minute=1),
            'options': {'queue': 'periodic'}
        },
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
        },
        'remove_csv_files': {
            'task': 'remove_csv_files',
            'schedule': crontab(minute=1, hour='0,1,2'),
            'options': {'queue': 'periodic'}
        }
    }
    CELERY_QUEUES = [
        Queue('periodic', Exchange('default'), routing_key='periodic'),
        Queue('process-job', Exchange('default'), routing_key='process-job'),
        Queue('retry', Exchange('default'), routing_key='retry'),
        Queue('notify', Exchange('default'), routing_key='notify')
    ]

    API_HOST_NAME = "http://localhost:6011"

    NOTIFICATIONS_ALERT = 5  # five mins
    FROM_NUMBER = 'development'

    STATSD_ENABLED = False
    STATSD_HOST = "statsd.hostedgraphite.com"
    STATSD_PORT = 8125

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200

    SIMULATED_EMAIL_ADDRESSES = ('simulate-delivered@notifications.service.gov.uk',
                                 'simulate-permanent-failure@notifications.service.gov.uk',
                                 'simulate-temporary-failure@notifications.service.gov.uk',
                                 )

    SIMULATED_SMS_NUMBERS = ('+447700900000', '+447700900111', '+447700900222')


######################
# Config overrides ###
######################

class Development(Config):
    NOTIFY_EMAIL_DOMAIN = 'notify.tools'
    CSV_UPLOAD_BUCKET_NAME = 'development-notifications-csv-upload'
    NOTIFY_ENVIRONMENT = 'development'
    NOTIFICATION_QUEUE_PREFIX = 'development'
    DEBUG = True
    SQLALCHEMY_ECHO = False
    CELERY_QUEUES = Config.CELERY_QUEUES + [
        Queue('db-sms', Exchange('default'), routing_key='db-sms'),
        Queue('send-sms', Exchange('default'), routing_key='send-sms'),
        Queue('db-email', Exchange('default'), routing_key='db-email'),
        Queue('send-email', Exchange('default'), routing_key='send-email'),
        Queue('research-mode', Exchange('default'), routing_key='research-mode')
    ]


class Test(Config):
    NOTIFY_EMAIL_DOMAIN = 'test.notify.com'
    FROM_NUMBER = 'testing'
    NOTIFY_ENVIRONMENT = 'test'
    DEBUG = True
    CSV_UPLOAD_BUCKET_NAME = 'test-notifications-csv-upload'
    STATSD_ENABLED = True
    STATSD_HOST = "localhost"
    STATSD_PORT = 1000
    CELERY_QUEUES = Config.CELERY_QUEUES + [
        Queue('db-sms', Exchange('default'), routing_key='db-sms'),
        Queue('send-sms', Exchange('default'), routing_key='send-sms'),
        Queue('db-email', Exchange('default'), routing_key='db-email'),
        Queue('send-email', Exchange('default'), routing_key='send-email'),
        Queue('research-mode', Exchange('default'), routing_key='research-mode')
    ]


class Preview(Config):
    NOTIFY_EMAIL_DOMAIN = 'notify.works'
    NOTIFY_ENVIRONMENT = 'preview'
    CSV_UPLOAD_BUCKET_NAME = 'preview-notifications-csv-upload'
    API_HOST_NAME = 'http://admin-api.internal'
    FROM_NUMBER = 'preview'


class Staging(Config):
    NOTIFY_EMAIL_DOMAIN = 'staging-notify.works'
    NOTIFY_ENVIRONMENT = 'staging'
    CSV_UPLOAD_BUCKET_NAME = 'staging-notify-csv-upload'
    STATSD_ENABLED = True
    API_HOST_NAME = 'http://admin-api.internal'
    FROM_NUMBER = 'stage'


class Live(Config):
    NOTIFY_EMAIL_DOMAIN = 'notifications.service.gov.uk'
    NOTIFY_ENVIRONMENT = 'live'
    CSV_UPLOAD_BUCKET_NAME = 'live-notifications-csv-upload'
    STATSD_ENABLED = True
    API_HOST_NAME = 'http://admin-api.internal'
    FROM_NUMBER = '40604'


configs = {
    'development': Development,
    'test': Test,
    'live': Live,
    'staging': Staging,
    'preview': Preview
}
