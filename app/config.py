from datetime import timedelta, time
import os
import json

from celery.schedules import crontab
from kombu import Exchange, Queue

from app.models import (
    EMAIL_TYPE, SMS_TYPE, LETTER_TYPE,
    KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST
)

if os.environ.get('VCAP_SERVICES'):
    # on cloudfoundry, config is a json blob in VCAP_SERVICES - unpack it, and populate
    # standard environment variables from it
    from app.cloudfoundry_config import extract_cloudfoundry_config

    extract_cloudfoundry_config()


class QueueNames(object):
    PERIODIC = 'periodic-tasks'
    PRIORITY = 'priority-tasks'
    DATABASE = 'database-tasks'
    SEND_SMS = 'send-sms-tasks'
    SEND_EMAIL = 'send-email-tasks'
    RESEARCH_MODE = 'research-mode-tasks'
    STATISTICS = 'statistics-tasks'
    JOBS = 'job-tasks'
    RETRY = 'retry-tasks'
    NOTIFY = 'notify-internal-tasks'
    PROCESS_FTP = 'process-ftp-tasks'
    CREATE_LETTERS_PDF = 'create-letters-pdf-tasks'
    CALLBACKS = 'service-callbacks'
    LETTERS = 'letter-tasks'

    @staticmethod
    def all_queues():
        return [
            QueueNames.PRIORITY,
            QueueNames.PERIODIC,
            QueueNames.DATABASE,
            QueueNames.SEND_SMS,
            QueueNames.SEND_EMAIL,
            QueueNames.RESEARCH_MODE,
            QueueNames.STATISTICS,
            QueueNames.JOBS,
            QueueNames.RETRY,
            QueueNames.NOTIFY,
            QueueNames.CREATE_LETTERS_PDF,
            QueueNames.CALLBACKS,
            QueueNames.LETTERS,
        ]


class TaskNames(object):
    DVLA_JOBS = 'send-jobs-to-dvla'
    DVLA_NOTIFICATIONS = 'send-api-notifications-to-dvla'
    PROCESS_INCOMPLETE_JOBS = 'process-incomplete-jobs'


class Config(object):
    # URL of admin app
    ADMIN_BASE_URL = os.environ['ADMIN_BASE_URL']

    # URL of api app (on AWS this is the internal api endpoint)
    API_HOST_NAME = os.getenv('API_HOST_NAME')

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

    # URL of redis instance
    REDIS_URL = os.getenv('REDIS_URL')
    REDIS_ENABLED = os.getenv('REDIS_ENABLED') == '1'
    EXPIRE_CACHE_IN_SECONDS = 600

    # Performance platform
    PERFORMANCE_PLATFORM_ENABLED = False
    PERFORMANCE_PLATFORM_URL = 'https://www.performance.service.gov.uk/data/govuk-notify/'
    PERFORMANCE_PLATFORM_TOKEN = os.getenv('PERFORMANCE_PLATFORM_TOKEN')

    # Logging
    DEBUG = False
    NOTIFY_LOG_PATH = os.getenv('NOTIFY_LOG_PATH')

    ###########################
    # Default config values ###
    ###########################

    NOTIFY_ENVIRONMENT = 'development'
    ADMIN_CLIENT_USER_NAME = 'notify-admin'
    AWS_REGION = 'eu-west-1'
    INVITATION_EXPIRATION_DAYS = 2
    NOTIFY_APP_NAME = 'api'
    SQLALCHEMY_COMMIT_ON_TEARDOWN = False
    SQLALCHEMY_RECORD_QUERIES = True
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    PAGE_SIZE = 50
    API_PAGE_SIZE = 250
    SMS_CHAR_COUNT_LIMIT = 495
    TEST_MESSAGE_FILENAME = 'Test message'
    ONE_OFF_MESSAGE_FILENAME = 'Report'
    MAX_VERIFY_CODE_COUNT = 10

    CHECK_PROXY_HEADER = False

    NOTIFY_SERVICE_ID = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
    NOTIFY_USER_ID = '6af522d0-2915-4e52-83a3-3690455a5fe6'
    INVITATION_EMAIL_TEMPLATE_ID = '4f46df42-f795-4cc4-83bb-65ca312f49cc'
    SMS_CODE_TEMPLATE_ID = '36fb0730-6259-4da1-8a80-c8de22ad4246'
    EMAIL_2FA_TEMPLATE_ID = '299726d2-dba6-42b8-8209-30e1d66ea164'
    NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID = 'ece42649-22a8-4d06-b87f-d52d5d3f0a27'
    PASSWORD_RESET_TEMPLATE_ID = '474e9242-823b-4f99-813d-ed392e7f1201'
    ALREADY_REGISTERED_EMAIL_TEMPLATE_ID = '0880fbb1-a0c6-46f0-9a8e-36c986381ceb'
    CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID = 'eb4d9930-87ab-4aef-9bce-786762687884'
    SERVICE_NOW_LIVE_TEMPLATE_ID = '618185c6-3636-49cd-b7d2-6f6f5eb3bdde'

    BROKER_URL = 'sqs://'
    BROKER_TRANSPORT_OPTIONS = {
        'region': AWS_REGION,
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 310,
        'queue_name_prefix': NOTIFICATION_QUEUE_PREFIX
    }
    CELERY_ENABLE_UTC = True
    CELERY_TIMEZONE = 'Europe/London'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_IMPORTS = ('app.celery.tasks', 'app.celery.scheduled_tasks')
    CELERYBEAT_SCHEDULE = {
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
            'schedule': crontab(hour=0, minute=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-email-notifications': {
            'task': 'delete-email-notifications',
            'schedule': crontab(hour=0, minute=20),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-letter-notifications': {
            'task': 'delete-letter-notifications',
            'schedule': crontab(hour=0, minute=40),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'delete-inbound-sms': {
            'task': 'delete-inbound-sms',
            'schedule': crontab(hour=1, minute=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'send-daily-performance-platform-stats': {
            'task': 'send-daily-performance-platform-stats',
            'schedule': crontab(hour=2, minute=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'switch-current-sms-provider-on-slow-delivery': {
            'task': 'switch-current-sms-provider-on-slow-delivery',
            'schedule': crontab(),  # Every minute
            'options': {'queue': QueueNames.PERIODIC}
        },
        'timeout-sending-notifications': {
            'task': 'timeout-sending-notifications',
            'schedule': crontab(hour=3, minute=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'remove_sms_email_jobs': {
            'task': 'remove_csv_files',
            'schedule': crontab(hour=4, minute=0),
            'options': {'queue': QueueNames.PERIODIC},
            'kwargs': {'job_types': [EMAIL_TYPE, SMS_TYPE]}
        },
        'remove_letter_jobs': {
            'task': 'remove_csv_files',
            'schedule': crontab(hour=4, minute=20),
            'options': {'queue': QueueNames.PERIODIC},
            'kwargs': {'job_types': [LETTER_TYPE]}
        },
        'remove_transformed_dvla_files': {
            'task': 'remove_transformed_dvla_files',
            'schedule': crontab(hour=4, minute=40),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'timeout-job-statistics': {
            'task': 'timeout-job-statistics',
            'schedule': crontab(hour=5, minute=0),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'populate_monthly_billing': {
            'task': 'populate_monthly_billing',
            'schedule': crontab(hour=5, minute=10),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'run-letter-jobs': {
            'task': 'run-letter-jobs',
            'schedule': crontab(hour=17, minute=30),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'trigger-letter-pdfs-for-day': {
            'task': 'trigger-letter-pdfs-for-day',
            'schedule': crontab(hour=17, minute=50),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'run-letter-api-notifications': {
            'task': 'run-letter-api-notifications',
            'schedule': crontab(hour=17, minute=40),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'check-job-status': {
            'task': 'check-job-status',
            'schedule': crontab(),
            'options': {'queue': QueueNames.PERIODIC}
        },
        'daily-stats-template-usage-by-month': {
            'task': 'daily-stats-template-usage-by-month',
            'schedule': crontab(hour=0, minute=50),
            'options': {'queue': QueueNames.PERIODIC}
        }
    }
    CELERY_QUEUES = []

    NOTIFICATIONS_ALERT = 5  # five mins
    FROM_NUMBER = 'development'

    STATSD_ENABLED = False
    STATSD_HOST = "statsd.hostedgraphite.com"
    STATSD_PORT = 8125

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200  # 3 days

    SIMULATED_EMAIL_ADDRESSES = (
        'simulate-delivered@notifications.service.gov.uk',
        'simulate-delivered-2@notifications.service.gov.uk',
        'simulate-delivered-3@notifications.service.gov.uk',
    )

    SIMULATED_SMS_NUMBERS = ('+447700900000', '+447700900111', '+447700900222')

    FUNCTIONAL_TEST_PROVIDER_SERVICE_ID = None
    FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID = None

    DVLA_BUCKETS = {
        'job': '{}-dvla-file-per-job'.format(os.getenv('NOTIFY_ENVIRONMENT')),
        'notification': '{}-dvla-letter-api-files'.format(os.getenv('NOTIFY_ENVIRONMENT'))
    }

    API_KEY_LIMITS = {
        KEY_TYPE_TEAM: {
            "limit": 3000,
            "interval": 60
        },
        KEY_TYPE_NORMAL: {
            "limit": 3000,
            "interval": 60
        },
        KEY_TYPE_TEST: {
            "limit": 3000,
            "interval": 60
        }
    }

    FREE_SMS_TIER_FRAGMENT_COUNT = 250000

    SMS_INBOUND_WHITELIST = json.loads(os.environ.get('SMS_INBOUND_WHITELIST', '[]'))
    FIRETEXT_INBOUND_SMS_AUTH = json.loads(os.environ.get('FIRETEXT_INBOUND_SMS_AUTH', '[]'))
    MMG_INBOUND_SMS_AUTH = json.loads(os.environ.get('MMG_INBOUND_SMS_AUTH', '[]'))
    MMG_INBOUND_SMS_USERNAME = json.loads(os.environ.get('MMG_INBOUND_SMS_USERNAME', '[]'))

    ROUTE_SECRET_KEY_1 = os.environ.get('ROUTE_SECRET_KEY_1', '')
    ROUTE_SECRET_KEY_2 = os.environ.get('ROUTE_SECRET_KEY_2', '')

    # Format is as follows:
    # {"dataset_1": "token_1", ...}
    PERFORMANCE_PLATFORM_ENDPOINTS = json.loads(os.environ.get('PERFORMANCE_PLATFORM_ENDPOINTS', '{}'))

    TEMPLATE_PREVIEW_API_HOST = os.environ.get('TEMPLATE_PREVIEW_API_HOST', 'http://localhost:6013')
    TEMPLATE_PREVIEW_API_KEY = os.environ.get('TEMPLATE_PREVIEW_API_KEY', 'my-secret-key')

    LETTER_PROCESSING_DEADLINE = time(17, 30)


######################
# Config overrides ###
######################

class Development(Config):
    NOTIFY_LOG_PATH = 'application.log'
    SQLALCHEMY_ECHO = False
    NOTIFY_EMAIL_DOMAIN = 'notify.tools'
    CSV_UPLOAD_BUCKET_NAME = 'development-notifications-csv-upload'
    LETTERS_PDF_BUCKET_NAME = 'development-letters-pdf'
    DVLA_RESPONSE_BUCKET_NAME = 'notify.tools-ftp'
    NOTIFY_ENVIRONMENT = 'development'
    NOTIFICATION_QUEUE_PREFIX = 'development'
    DEBUG = True

    for queue in QueueNames.all_queues():
        Config.CELERY_QUEUES.append(
            Queue(queue, Exchange('default'), routing_key=queue)
        )

    API_HOST_NAME = "http://localhost:6011"
    API_RATE_LIMIT_ENABLED = True


class Test(Config):
    NOTIFY_EMAIL_DOMAIN = 'test.notify.com'
    FROM_NUMBER = 'testing'
    NOTIFY_ENVIRONMENT = 'test'
    DEBUG = True
    TESTING = True
    CSV_UPLOAD_BUCKET_NAME = 'test-notifications-csv-upload'
    LETTERS_PDF_BUCKET_NAME = 'test-letters-pdf'
    DVLA_RESPONSE_BUCKET_NAME = 'test.notify.com-ftp'
    STATSD_ENABLED = True
    STATSD_HOST = "localhost"
    STATSD_PORT = 1000

    BROKER_URL = 'you-forgot-to-mock-celery-in-your-tests://'

    for queue in QueueNames.all_queues():
        Config.CELERY_QUEUES.append(
            Queue(queue, Exchange('default'), routing_key=queue)
        )

    API_RATE_LIMIT_ENABLED = True
    API_HOST_NAME = "http://localhost:6011"

    API_KEY_LIMITS = {
        KEY_TYPE_TEAM: {
            "limit": 1,
            "interval": 2
        },
        KEY_TYPE_NORMAL: {
            "limit": 10,
            "interval": 20
        },
        KEY_TYPE_TEST: {
            "limit": 100,
            "interval": 200
        }
    }

    SMS_INBOUND_WHITELIST = ['203.0.113.195']
    FIRETEXT_INBOUND_SMS_AUTH = ['testkey']
    MMG_INBOUND_SMS_AUTH = ['testkey']
    MMG_INBOUND_SMS_USERNAME = ['username']
    TEMPLATE_PREVIEW_API_HOST = 'http://localhost:9999'


class Preview(Config):
    NOTIFY_EMAIL_DOMAIN = 'notify.works'
    NOTIFY_ENVIRONMENT = 'preview'
    CSV_UPLOAD_BUCKET_NAME = 'preview-notifications-csv-upload'
    LETTERS_PDF_BUCKET_NAME = 'preview-letters-pdf'
    DVLA_RESPONSE_BUCKET_NAME = 'notify.works-ftp'
    FROM_NUMBER = 'preview'
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True


class Staging(Config):
    NOTIFY_EMAIL_DOMAIN = 'staging-notify.works'
    NOTIFY_ENVIRONMENT = 'staging'
    CSV_UPLOAD_BUCKET_NAME = 'staging-notify-csv-upload'
    LETTERS_PDF_BUCKET_NAME = 'staging-letters-pdf'
    DVLA_RESPONSE_BUCKET_NAME = 'staging-notify.works-ftp'
    STATSD_ENABLED = True
    FROM_NUMBER = 'stage'
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True
    REDIS_ENABLED = True
    SQLALCHEMY_POOL_TIMEOUT = 30
    SQLALCHEMY_POOL_RECYCLE = 300

    API_KEY_LIMITS = {
        KEY_TYPE_TEAM: {
            "limit": 24000,
            "interval": 60
        },
        KEY_TYPE_NORMAL: {
            "limit": 24000,
            "interval": 60
        },
        KEY_TYPE_TEST: {
            "limit": 24000,
            "interval": 60
        }
    }


class Live(Config):
    NOTIFY_EMAIL_DOMAIN = 'notifications.service.gov.uk'
    NOTIFY_ENVIRONMENT = 'live'
    CSV_UPLOAD_BUCKET_NAME = 'live-notifications-csv-upload'
    LETTERS_PDF_BUCKET_NAME = 'production-letters-pdf'
    DVLA_RESPONSE_BUCKET_NAME = 'notifications.service.gov.uk-ftp'
    STATSD_ENABLED = True
    FROM_NUMBER = 'GOVUK'
    FUNCTIONAL_TEST_PROVIDER_SERVICE_ID = '6c1d81bb-dae2-4ee9-80b0-89a4aae9f649'
    FUNCTIONAL_TEST_PROVIDER_SMS_TEMPLATE_ID = 'ba9e1789-a804-40b8-871f-cc60d4c1286f'
    PERFORMANCE_PLATFORM_ENABLED = True
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True


class CloudFoundryConfig(Config):
    pass


# CloudFoundry sandbox
class Sandbox(CloudFoundryConfig):
    NOTIFY_EMAIL_DOMAIN = 'notify.works'
    NOTIFY_ENVIRONMENT = 'sandbox'
    CSV_UPLOAD_BUCKET_NAME = 'cf-sandbox-notifications-csv-upload'
    LETTERS_PDF_BUCKET_NAME = 'cf-sandbox-letters-pdf'
    DVLA_RESPONSE_BUCKET_NAME = 'notify.works-ftp'
    FROM_NUMBER = 'sandbox'
    REDIS_ENABLED = False


configs = {
    'development': Development,
    'test': Test,
    'live': Live,
    'production': Live,
    'staging': Staging,
    'preview': Preview,
    'sandbox': Sandbox
}
