import os
from datetime import timedelta


class Config(object):
    DEBUG = False
    ADMIN_CLIENT_USER_NAME = os.environ['ADMIN_CLIENT_USER_NAME']
    ADMIN_CLIENT_SECRET = os.environ['ADMIN_CLIENT_SECRET']
    AWS_REGION = os.environ['AWS_REGION']
    DANGEROUS_SALT = os.environ['DANGEROUS_SALT']
    DELIVERY_CLIENT_USER_NAME = os.environ['DELIVERY_CLIENT_USER_NAME']
    DELIVERY_CLIENT_SECRET = os.environ['DELIVERY_CLIENT_SECRET']
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

    BROKER_URL = 'sqs://'
    BROKER_TRANSPORT_OPTIONS = {
        'region': 'eu-west-1',
        'polling_interval': 10,  # 1 second
        'visibility_timeout': 3600,  # 1 hour
        'queue_name_prefix': 'NOTIFY-CELERY-TEST-'
    }
    CELERY_ENABLE_UTC = True,
    CELERY_TIMEZONE = 'Europe/London'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    # CELERYBEAT_SCHEDULE = {
    #     'refresh-queues': {
    #         'task': 'refresh-services',
    #         'schedule': timedelta(seconds=5)
    #     }
    # }
    CELERY_IMPORTS = ('app.celery.tasks',)
    TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_NUMBER = os.getenv('TWILIO_NUMBER')


class Development(Config):
    DEBUG = True


class Test(Development):
    pass
