import os
from config import Config


class Staging(Config):
    ADMIN_BASE_URL = os.environ['STAGING_ADMIN_BASE_URL']
    API_HOST_NAME = os.environ['STAGING_API_HOST_NAME']
    ADMIN_CLIENT_SECRET = os.environ['STAGING_ADMIN_CLIENT_SECRET']
    DANGEROUS_SALT = os.environ['STAGING_DANGEROUS_SALT']
    NOTIFICATION_QUEUE_PREFIX = os.environ['STAGING_NOTIFICATION_QUEUE_PREFIX']
    NOTIFY_JOB_QUEUE = os.environ['STAGING_NOTIFY_JOB_QUEUE']
    SECRET_KEY = os.environ['STAGING_SECRET_KEY']
    SQLALCHEMY_DATABASE_URI = os.environ['STAGING_SQLALCHEMY_DATABASE_URI']
    VERIFY_CODE_FROM_EMAIL_ADDRESS = os.environ['STAGING_VERIFY_CODE_FROM_EMAIL_ADDRESS']
    NOTIFY_EMAIL_DOMAIN = os.environ['STAGING_NOTIFY_EMAIL_DOMAIN']
    FIRETEXT_API_KEY = os.getenv("STAGING_FIRETEXT_API_KEY")
    MMG_API_KEY = os.environ['STAGING_MMG_API_KEY']
    CSV_UPLOAD_BUCKET_NAME = 'staging-notifications-csv-upload'
    FROM_NUMBER = os.getenv('STAGING_FROM_NUMBER')

    BROKER_TRANSPORT_OPTIONS = {
        'region': 'eu-west-1',
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 14410,  # 60 seconds
        'queue_name_prefix': os.environ['STAGING_NOTIFICATION_QUEUE_PREFIX'] + '-'
    }
