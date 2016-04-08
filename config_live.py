import os
from config import Config


class Live(Config):
    ADMIN_BASE_URL = os.environ['LIVE_ADMIN_BASE_URL']
    API_HOST_NAME = os.environ['LIVE_API_HOST_NAME']
    ADMIN_CLIENT_SECRET = os.environ['LIVE_ADMIN_CLIENT_SECRET']
    DANGEROUS_SALT = os.environ['LIVE_DANGEROUS_SALT']
    NOTIFICATION_QUEUE_PREFIX = os.environ['LIVE_NOTIFICATION_QUEUE_PREFIX']
    NOTIFY_JOB_QUEUE = os.environ['LIVE_NOTIFY_JOB_QUEUE']
    SECRET_KEY = os.environ['LIVE_SECRET_KEY']
    SQLALCHEMY_DATABASE_URI = os.environ['LIVE_SQLALCHEMY_DATABASE_URI']
    VERIFY_CODE_FROM_EMAIL_ADDRESS = os.environ['LIVE_VERIFY_CODE_FROM_EMAIL_ADDRESS']
    NOTIFY_EMAIL_DOMAIN = os.environ['LIVE_NOTIFY_EMAIL_DOMAIN']
    FIRETEXT_API_KEY = os.getenv("LIVE_FIRETEXT_API_KEY")
    FIRETEXT_NUMBER = os.getenv("LIVE_FIRETEXT_NUMBER")
    TWILIO_AUTH_TOKEN = os.getenv('LIVE_TWILIO_AUTH_TOKEN')
    MMG_API_KEY = os.environ['LIVE_MMG_API_KEY']

    BROKER_TRANSPORT_OPTIONS = {
        'region': 'eu-west-1',
        'polling_interval': 1,  # 1 second
        'visibility_timeout': 60,  # 60 seconds
        'queue_name_prefix': os.environ['LIVE_NOTIFICATION_QUEUE_PREFIX'] + '-'
    }
