import json
import os
from datetime import timedelta

from celery.schedules import crontab
from kombu import Exchange, Queue

if os.environ.get("VCAP_SERVICES"):
    # on cloudfoundry, config is a json blob in VCAP_SERVICES - unpack it, and populate
    # standard environment variables from it
    from app.cloudfoundry_config import extract_cloudfoundry_config

    extract_cloudfoundry_config()


class QueueNames(object):
    PERIODIC = "periodic-tasks"
    DATABASE = "database-tasks"
    SEND_SMS = "send-sms-tasks"
    SEND_EMAIL = "send-email-tasks"
    SEND_LETTER = "send-letter-tasks"
    RESEARCH_MODE = "research-mode-tasks"
    REPORTING = "reporting-tasks"
    JOBS = "job-tasks"
    RETRY = "retry-tasks"
    NOTIFY = "notify-internal-tasks"
    PROCESS_FTP = "process-ftp-tasks"
    CREATE_LETTERS_PDF = "create-letters-pdf-tasks"
    CALLBACKS = "service-callbacks"
    CALLBACKS_RETRY = "service-callbacks-retry"
    LETTERS = "letter-tasks"
    SES_CALLBACKS = "ses-callbacks"
    SMS_CALLBACKS = "sms-callbacks"
    ANTIVIRUS = "antivirus-tasks"
    SANITISE_LETTERS = "sanitise-letter-tasks"
    SAVE_API_EMAIL = "save-api-email-tasks"
    SAVE_API_SMS = "save-api-sms-tasks"
    BROADCASTS = "broadcast-tasks"
    GOVUK_ALERTS = "govuk-alerts"

    @staticmethod
    def all_queues():
        return [
            QueueNames.PERIODIC,
            QueueNames.DATABASE,
            QueueNames.SEND_SMS,
            QueueNames.SEND_EMAIL,
            QueueNames.SEND_LETTER,
            QueueNames.RESEARCH_MODE,
            QueueNames.REPORTING,
            QueueNames.JOBS,
            QueueNames.RETRY,
            QueueNames.NOTIFY,
            QueueNames.CREATE_LETTERS_PDF,
            QueueNames.CALLBACKS,
            QueueNames.CALLBACKS_RETRY,
            QueueNames.LETTERS,
            QueueNames.SES_CALLBACKS,
            QueueNames.SMS_CALLBACKS,
            QueueNames.SAVE_API_EMAIL,
            QueueNames.SAVE_API_SMS,
            QueueNames.BROADCASTS,
        ]


class BroadcastProvider:
    EE = "ee"
    VODAFONE = "vodafone"
    THREE = "three"
    O2 = "o2"

    PROVIDERS = [EE, VODAFONE, THREE, O2]


class TaskNames(object):
    PROCESS_INCOMPLETE_JOBS = "process-incomplete-jobs"
    ZIP_AND_SEND_LETTER_PDFS = "zip-and-send-letter-pdfs"
    SCAN_FILE = "scan-file"
    SANITISE_LETTER = "sanitise-and-upload-letter"
    CREATE_PDF_FOR_TEMPLATED_LETTER = "create-pdf-for-templated-letter"
    PUBLISH_GOVUK_ALERTS = "publish-govuk-alerts"
    RECREATE_PDF_FOR_PRECOMPILED_LETTER = "recreate-pdf-for-precompiled-letter"


class Config(object):
    # URL of admin app
    ADMIN_BASE_URL = os.getenv("ADMIN_BASE_URL", "http://localhost:6012")

    # URL of api app (on AWS this is the internal api endpoint)
    API_HOST_NAME = os.getenv("API_HOST_NAME")
    API_HOST_NAME_INTERNAL = os.getenv("API_HOST_NAME_INTERNAL")

    # secrets that internal apps, such as the admin app or document download, must use to authenticate with the API
    ADMIN_CLIENT_ID = "notify-admin"
    GOVUK_ALERTS_CLIENT_ID = "govuk-alerts"
    FUNCTIONAL_TESTS_CLIENT_ID = "notify-functional-tests"

    INTERNAL_CLIENT_API_KEYS = json.loads(os.environ.get("INTERNAL_CLIENT_API_KEYS", "{}"))

    # encyption secret/salt
    SECRET_KEY = os.getenv("SECRET_KEY")
    DANGEROUS_SALT = os.getenv("DANGEROUS_SALT")

    # DB conection string
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")

    # MMG API Key
    MMG_API_KEY = os.getenv("MMG_API_KEY")

    # Firetext API Key
    FIRETEXT_API_KEY = os.getenv("FIRETEXT_API_KEY")
    FIRETEXT_INTERNATIONAL_API_KEY = os.getenv("FIRETEXT_INTERNATIONAL_API_KEY", "placeholder")

    # Prefix to identify queues in SQS
    NOTIFICATION_QUEUE_PREFIX = os.getenv("NOTIFICATION_QUEUE_PREFIX")

    # URL of redis instance
    REDIS_URL = os.getenv("REDIS_URL")
    REDIS_ENABLED = False if os.environ.get("REDIS_ENABLED") == "0" else True
    EXPIRE_CACHE_TEN_MINUTES = 600
    EXPIRE_CACHE_EIGHT_DAYS = 8 * 24 * 60 * 60

    # Zendesk
    ZENDESK_API_KEY = os.environ.get("ZENDESK_API_KEY")

    # Logging
    DEBUG = False
    NOTIFY_LOG_PATH = os.getenv("NOTIFY_LOG_PATH")

    # Cronitor
    CRONITOR_ENABLED = False
    CRONITOR_KEYS = json.loads(os.environ.get("CRONITOR_KEYS", "{}"))

    # Antivirus
    ANTIVIRUS_ENABLED = True

    ###########################
    # Default config values ###
    ###########################

    NOTIFY_ENVIRONMENT = "development"
    AWS_REGION = "eu-west-1"
    INVITATION_EXPIRATION_DAYS = 2
    NOTIFY_APP_NAME = "api"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", 5)),
        "pool_timeout": 30,
        "pool_recycle": 300,
        "connect_args": {
            "options": "-c statement_timeout=1200000",
        },
    }
    PAGE_SIZE = 50
    API_PAGE_SIZE = 250
    TEST_MESSAGE_FILENAME = "Test message"
    ONE_OFF_MESSAGE_FILENAME = "Report"
    MAX_VERIFY_CODE_COUNT = 5
    MAX_FAILED_LOGIN_COUNT = 10

    # be careful increasing this size without being sure that we won't see slowness in pysftp
    MAX_LETTER_PDF_ZIP_FILESIZE = 40 * 1024 * 1024  # 40mb
    MAX_LETTER_PDF_COUNT_PER_ZIP = 500

    CHECK_PROXY_HEADER = False

    # these should always add up to 100%
    SMS_PROVIDER_RESTING_POINTS = {"mmg": 51, "firetext": 49}

    NOTIFY_SERVICE_ID = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"
    NOTIFY_USER_ID = "6af522d0-2915-4e52-83a3-3690455a5fe6"
    INVITATION_EMAIL_TEMPLATE_ID = "4f46df42-f795-4cc4-83bb-65ca312f49cc"
    BROADCAST_INVITATION_EMAIL_TEMPLATE_ID = "46152f7c-6901-41d5-8590-a5624d0d4359"
    SMS_CODE_TEMPLATE_ID = "36fb0730-6259-4da1-8a80-c8de22ad4246"
    EMAIL_2FA_TEMPLATE_ID = "299726d2-dba6-42b8-8209-30e1d66ea164"
    NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID = "ece42649-22a8-4d06-b87f-d52d5d3f0a27"
    PASSWORD_RESET_TEMPLATE_ID = "474e9242-823b-4f99-813d-ed392e7f1201"
    ALREADY_REGISTERED_EMAIL_TEMPLATE_ID = "0880fbb1-a0c6-46f0-9a8e-36c986381ceb"
    CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID = "eb4d9930-87ab-4aef-9bce-786762687884"
    SERVICE_NOW_LIVE_TEMPLATE_ID = "618185c6-3636-49cd-b7d2-6f6f5eb3bdde"
    ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID = "203566f0-d835-47c5-aa06-932439c86573"
    TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID = "c73f1d71-4049-46d5-a647-d013bdeca3f0"
    TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID = "8a31520f-4751-4789-8ea1-fe54496725eb"
    REPLY_TO_EMAIL_ADDRESS_VERIFICATION_TEMPLATE_ID = "a42f1d17-9404-46d5-a647-d013bdfca3e1"
    MOU_SIGNER_RECEIPT_TEMPLATE_ID = "4fd2e43c-309b-4e50-8fb8-1955852d9d71"
    MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID = "c20206d5-bf03-4002-9a90-37d5032d9e84"
    MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID = "522b6657-5ca5-4368-a294-6b527703bd0b"
    ORGANISATION_HAS_NEW_GO_LIVE_REQUEST_TEMPLATE_ID = "5c7cfc0f-c3f4-4bd6-9a84-5a144aad5425"
    NOTIFY_INTERNATIONAL_SMS_SENDER = "07984404008"
    LETTERS_VOLUME_EMAIL_TEMPLATE_ID = "11fad854-fd38-4a7c-bd17-805fb13dfc12"
    NHS_EMAIL_BRANDING_ID = "a7dc4e56-660b-4db7-8cff-12c37b12b5ea"
    NHS_LETTER_BRANDING_ID = "2cd354bb-6b85-eda3-c0ad-6b613150459f"
    # we only need real email in Live environment (production)
    DVLA_EMAIL_ADDRESSES = json.loads(os.environ.get("DVLA_EMAIL_ADDRESSES", "[]"))

    CELERY = {
        "broker_url": "https://sqs.eu-west-1.amazonaws.com",
        "broker_transport": "sqs",
        "broker_transport_options": {
            "region": AWS_REGION,
            "visibility_timeout": 310,
            "queue_name_prefix": NOTIFICATION_QUEUE_PREFIX,
            "is_secure": True,
        },
        "result_expires": 0,
        "timezone": "UTC",
        "imports": [
            "app.celery.tasks",
            "app.celery.scheduled_tasks",
            "app.celery.reporting_tasks",
            "app.celery.nightly_tasks",
        ],
        # this is overriden by the -Q command, but locally, we should read from all queues
        "task_queues": [Queue(queue, Exchange("default"), routing_key=queue) for queue in QueueNames.all_queues()],
        "beat_schedule": {
            # app/celery/scheduled_tasks.py
            "run-scheduled-jobs": {
                "task": "run-scheduled-jobs",
                "schedule": crontab(minute="0,15,30,45"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "delete-verify-codes": {
                "task": "delete-verify-codes",
                "schedule": timedelta(minutes=63),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "delete-invitations": {
                "task": "delete-invitations",
                "schedule": timedelta(minutes=66),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "generate-sms-delivery-stats": {
                "task": "generate-sms-delivery-stats",
                "schedule": crontab(),  # Every minute
                "options": {"queue": QueueNames.PERIODIC},
            },
            "switch-current-sms-provider-on-slow-delivery": {
                "task": "switch-current-sms-provider-on-slow-delivery",
                "schedule": crontab(),  # Every minute
                "options": {"queue": QueueNames.PERIODIC},
            },
            "check-job-status": {
                "task": "check-job-status",
                "schedule": crontab(),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "tend-providers-back-to-middle": {
                "task": "tend-providers-back-to-middle",
                "schedule": crontab(minute="*/5"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "check-for-missing-rows-in-completed-jobs": {
                "task": "check-for-missing-rows-in-completed-jobs",
                "schedule": crontab(minute="*/10"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "replay-created-notifications": {
                "task": "replay-created-notifications",
                "schedule": crontab(minute="0, 15, 30, 45"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "run-populate-annual-billing": {
                "task": "run-populate-annual-billing",
                "schedule": crontab(minute=1, hour=2, day_of_month=1, month_of_year=4),
                "options": {"queue": QueueNames.PERIODIC},
            },
            # app/celery/nightly_tasks.py
            "timeout-sending-notifications": {
                "task": "timeout-sending-notifications",
                "schedule": crontab(hour=0, minute=5),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "create-nightly-billing": {
                "task": "create-nightly-billing",
                "schedule": crontab(hour=0, minute=15),
                "options": {"queue": QueueNames.REPORTING},
            },
            "update-ft-billing-for-today": {
                "task": "update-ft-billing-for-today",
                "schedule": crontab(hour="*", minute=0),
                "options": {"queue": QueueNames.REPORTING},
            },
            "create-nightly-notification-status": {
                "task": "create-nightly-notification-status",
                "schedule": crontab(hour=0, minute=30),  # after 'timeout-sending-notifications'
                "options": {"queue": QueueNames.REPORTING},
            },
            "delete-notifications-older-than-retention": {
                "task": "delete-notifications-older-than-retention",
                "schedule": crontab(hour=3, minute=0),  # after 'create-nightly-notification-status'
                "options": {"queue": QueueNames.REPORTING},
            },
            "delete-inbound-sms": {
                "task": "delete-inbound-sms",
                "schedule": crontab(hour=1, minute=40),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "save-daily-notification-processing-time": {
                "task": "save-daily-notification-processing-time",
                "schedule": crontab(hour=2, minute=0),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "remove_sms_email_jobs": {
                "task": "remove_sms_email_jobs",
                "schedule": crontab(hour=4, minute=0),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "remove_letter_jobs": {
                "task": "remove_letter_jobs",
                "schedule": crontab(hour=4, minute=20),
                # since we mark jobs as archived
                "options": {"queue": QueueNames.PERIODIC},
            },
            "check-if-letters-still-in-created": {
                "task": "check-if-letters-still-in-created",
                "schedule": crontab(day_of_week="mon-fri", hour=7, minute=0),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "check-if-letters-still-pending-virus-check": {
                "task": "check-if-letters-still-pending-virus-check",
                "schedule": crontab(day_of_week="mon-fri", hour="9,15", minute=0),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "check-for-services-with-high-failure-rates-or-sending-to-tv-numbers": {
                "task": "check-for-services-with-high-failure-rates-or-sending-to-tv-numbers",
                "schedule": crontab(day_of_week="mon-fri", hour=10, minute=30),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "raise-alert-if-letter-notifications-still-sending": {
                "task": "raise-alert-if-letter-notifications-still-sending",
                "schedule": crontab(hour=17, minute=00),
                "options": {"queue": QueueNames.PERIODIC},
            },
            # The check-time-to-collate-letters does assume it is called in an hour that BST does not make a
            # difference to the truncate date which translates to the filename to process
            # We schedule it for 16:50 and 17:50 UTC. This task is then responsible for determining if the local time
            # is 17:50, and if so, actually kicking off letter collation.
            # If updating the cron schedule, you should update the task as well - at least while we're still processing
            # letters by FTP. With the API changes we should have more flexibility.
            "check-time-to-collate-letters": {
                "task": "check-time-to-collate-letters",
                "schedule": crontab(hour="16,17", minute=50),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "raise-alert-if-no-letter-ack-file": {
                "task": "raise-alert-if-no-letter-ack-file",
                "schedule": crontab(hour=22, minute=45),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "delete-old-records-from-events-table": {
                "task": "delete-old-records-from-events-table",
                "schedule": crontab(hour=3, minute=4),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "zendesk-new-email-branding-report": {
                "task": "zendesk-new-email-branding-report",
                "schedule": crontab(hour=0, minute=30, day_of_week="mon-fri"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "check-for-low-available-inbound-sms-numbers": {
                "task": "check-for-low-available-inbound-sms-numbers",
                "schedule": crontab(hour=9, minute=0, day_of_week="mon"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "weekly-dwp-report": {
                "task": "weekly-dwp-report",
                "schedule": crontab(hour=9, minute=0, day_of_week="mon"),
                "options": {"queue": QueueNames.REPORTING},
            },
            # first tuesday of every month
            "change-dvla-api-key": {
                "task": "change-dvla-api-key",
                "schedule": crontab(hour=9, minute=0, day_of_week="tue", day_of_month="1-7"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            # the wednesday immediately following the first tuesday of every month
            "change-dvla-password": {
                "task": "change-dvla-password",
                "schedule": crontab(hour=9, minute=0, day_of_week="wed", day_of_month="2-8"),
                "options": {"queue": QueueNames.PERIODIC},
            },
        },
    }

    # we can set celeryd_prefetch_multiplier to be 1 for celery apps which handle only long running tasks
    if os.getenv("CELERYD_PREFETCH_MULTIPLIER"):
        CELERY["worker_prefetch_multiplier"] = os.getenv("CELERYD_PREFETCH_MULTIPLIER")

    FROM_NUMBER = "development"

    STATSD_HOST = os.getenv("STATSD_HOST")
    STATSD_PORT = 8125
    STATSD_ENABLED = bool(STATSD_HOST)

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200  # 3 days

    SIMULATED_EMAIL_ADDRESSES = (
        "simulate-delivered@notifications.service.gov.uk",
        "simulate-delivered-2@notifications.service.gov.uk",
        "simulate-delivered-3@notifications.service.gov.uk",
    )

    SIMULATED_SMS_NUMBERS = ("+447700900000", "+447700900111", "+447700900222")

    FREE_SMS_TIER_FRAGMENT_COUNT = 250000

    SMS_INBOUND_WHITELIST = json.loads(os.environ.get("SMS_INBOUND_WHITELIST", "[]"))
    FIRETEXT_INBOUND_SMS_AUTH = json.loads(os.environ.get("FIRETEXT_INBOUND_SMS_AUTH", "[]"))
    MMG_INBOUND_SMS_AUTH = json.loads(os.environ.get("MMG_INBOUND_SMS_AUTH", "[]"))
    MMG_INBOUND_SMS_USERNAME = json.loads(os.environ.get("MMG_INBOUND_SMS_USERNAME", "[]"))
    LOW_INBOUND_SMS_NUMBER_THRESHOLD = 50
    ROUTE_SECRET_KEY_1 = os.environ.get("ROUTE_SECRET_KEY_1", "")
    ROUTE_SECRET_KEY_2 = os.environ.get("ROUTE_SECRET_KEY_2", "")

    HIGH_VOLUME_SERVICE = json.loads(os.environ.get("HIGH_VOLUME_SERVICE", "[]"))

    TEMPLATE_PREVIEW_API_HOST = os.environ.get("TEMPLATE_PREVIEW_API_HOST", "http://localhost:6013")
    TEMPLATE_PREVIEW_API_KEY = os.environ.get("TEMPLATE_PREVIEW_API_KEY", "my-secret-key")

    DOCUMENT_DOWNLOAD_API_HOST = os.environ.get("DOCUMENT_DOWNLOAD_API_HOST", "http://localhost:7000")
    DOCUMENT_DOWNLOAD_API_HOST_INTERNAL = os.environ.get("DOCUMENT_DOWNLOAD_API_HOST_INTERNAL", "http://localhost:7000")
    DOCUMENT_DOWNLOAD_API_KEY = os.environ.get("DOCUMENT_DOWNLOAD_API_KEY", "auth-token")

    # these environment vars aren't defined in the manifest so to set them on paas use `cf set-env`
    MMG_URL = os.environ.get("MMG_URL", "https://api.mmg.co.uk/jsonv2a/api.php")
    FIRETEXT_URL = os.environ.get("FIRETEXT_URL", "https://www.firetext.co.uk/api/sendsms/json")
    SES_STUB_URL = os.environ.get("SES_STUB_URL")

    AWS_REGION = "eu-west-1"

    CBC_PROXY_ENABLED = True
    CBC_PROXY_AWS_ACCESS_KEY_ID = os.environ.get("CBC_PROXY_AWS_ACCESS_KEY_ID", "")
    CBC_PROXY_AWS_SECRET_ACCESS_KEY = os.environ.get("CBC_PROXY_AWS_SECRET_ACCESS_KEY", "")

    ENABLED_CBCS = {BroadcastProvider.EE, BroadcastProvider.THREE, BroadcastProvider.O2, BroadcastProvider.VODAFONE}

    # as defined in api db migration 0331_add_broadcast_org.py
    BROADCAST_ORGANISATION_ID = "38e4bf69-93b0-445d-acee-53ea53fe02df"

    DVLA_API_ENABLED = os.environ.get("DVLA_API_ENABLED") == "1"
    DVLA_API_POSTAGE_TYPE_EXCLUDE_LIST = json.loads(os.environ.get("DVLA_API_POSTAGE_TYPE_EXCLUDE_LIST", "[]"))
    DVLA_API_BASE_URL = os.environ.get("DVLA_API_BASE_URL", "https://uat.driver-vehicle-licensing.api.gov.uk")
    DVLA_API_TLS_CIPHERS = os.environ.get("DVLA_API_TLS_CIPHERS")

    # We don't expect to have any zendesk reporting beyond this. If someone is looking here and thinking of adding
    # something new, let's consider a more holistic approach first please. We should be revisiting this approach in
    # Q1 2023.
    # Our manifest builder takes our JSON string from notifications-credentials and passes it through the Jinja2
    # `tojson` filter, which escapes things like ' < > to their \uxxxx form. We need to turn those back into
    # real characters. We do that by turning the env var unicode string to bytes and then decoding that back to
    # a unicode string via the unicode-escape encoding, which will automatically decode \uxxxx forms back to their
    # basic representation.
    ZENDESK_REPORTING = json.loads(os.environ.get("ZENDESK_REPORTING", "{}").encode().decode("unicode-escape"))


######################
# Config overrides ###
######################


class Development(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = False

    SERVER_NAME = os.getenv("SERVER_NAME")

    REDIS_ENABLED = os.getenv("REDIS_ENABLED") == "1"

    S3_BUCKET_CSV_UPLOAD = "development-notifications-csv-upload"
    S3_BUCKET_CONTACT_LIST = "development-contact-list"
    S3_BUCKET_TEST_LETTERS = "development-test-letters"
    S3_BUCKET_DVLA_RESPONSE = "notify.tools-ftp"
    S3_BUCKET_LETTERS_PDF = "development-letters-pdf"
    S3_BUCKET_LETTERS_SCAN = "development-letters-scan"
    S3_BUCKET_INVALID_PDF = "development-letters-invalid-pdf"
    S3_BUCKET_TRANSIENT_UPLOADED_LETTERS = "development-transient-uploaded-letters"
    S3_BUCKET_LETTER_SANITISE = "development-letters-sanitise"

    INTERNAL_CLIENT_API_KEYS = {
        Config.ADMIN_CLIENT_ID: ["dev-notify-secret-key"],
        Config.GOVUK_ALERTS_CLIENT_ID: ["govuk-alerts-secret-key"],
        Config.FUNCTIONAL_TESTS_CLIENT_ID: ["functional-tests-secret-key"],
    }

    SECRET_KEY = "dev-notify-secret-key"
    DANGEROUS_SALT = "dev-notify-salt"

    MMG_INBOUND_SMS_AUTH = ["testkey"]
    MMG_INBOUND_SMS_USERNAME = ["username"]

    NOTIFY_ENVIRONMENT = "development"
    NOTIFY_LOG_PATH = "application.log"
    NOTIFY_EMAIL_DOMAIN = "notify.tools"

    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI", "postgresql://localhost/notification_api")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    ANTIVIRUS_ENABLED = os.getenv("ANTIVIRUS_ENABLED") == "1"

    API_HOST_NAME = os.getenv("API_HOST_NAME", "http://localhost:6011")
    API_HOST_NAME_INTERNAL = os.getenv("API_HOST_NAME_INTERNAL", "http://localhost:6011")
    API_RATE_LIMIT_ENABLED = True
    DVLA_EMAIL_ADDRESSES = ["success@simulator.amazonses.com"]

    CBC_PROXY_ENABLED = False


class Test(Development):
    NOTIFY_EMAIL_DOMAIN = "test.notify.com"
    FROM_NUMBER = "testing"
    NOTIFY_ENVIRONMENT = "test"
    TESTING = True

    HIGH_VOLUME_SERVICE = [
        "941b6f9a-50d7-4742-8d50-f365ca74bf27",
        "63f95b86-2d19-4497-b8b2-ccf25457df4e",
        "7e5950cb-9954-41f5-8376-962b8c8555cf",
        "10d1b9c9-0072-4fa9-ae1c-595e333841da",
    ]

    S3_BUCKET_CSV_UPLOAD = "test-notifications-csv-upload"
    S3_BUCKET_CONTACT_LIST = "test-contact-list"
    S3_BUCKET_TEST_LETTERS = "test-test-letters"
    S3_BUCKET_DVLA_RESPONSE = "test.notify.com-ftp"
    S3_BUCKET_LETTERS_PDF = "test-letters-pdf"
    S3_BUCKET_LETTERS_SCAN = "test-letters-scan"
    S3_BUCKET_INVALID_PDF = "test-letters-invalid-pdf"
    S3_BUCKET_TRANSIENT_UPLOADED_LETTERS = "test-transient-uploaded-letters"
    S3_BUCKET_LETTER_SANITISE = "test-letters-sanitise"

    # when testing, the SQLALCHEMY_DATABASE_URI is used for the postgres server's location
    # but the database name is set in the _notify_db fixture
    SQLALCHEMY_RECORD_QUERIES = True

    CELERY = {**Config.CELERY, "broker_url": "you-forgot-to-mock-celery-in-your-tests://"}

    ANTIVIRUS_ENABLED = True

    API_RATE_LIMIT_ENABLED = True
    API_HOST_NAME = "http://localhost:6011"
    API_HOST_NAME_INTERNAL = "http://localhost:6011"

    SMS_INBOUND_WHITELIST = ["203.0.113.195"]
    FIRETEXT_INBOUND_SMS_AUTH = ["testkey"]
    TEMPLATE_PREVIEW_API_HOST = "http://localhost:9999"

    MMG_URL = "https://example.com/mmg"
    FIRETEXT_URL = "https://example.com/firetext"

    CBC_PROXY_ENABLED = True
    DVLA_EMAIL_ADDRESSES = ["success@simulator.amazonses.com", "success+2@simulator.amazonses.com"]

    DVLA_API_BASE_URL = "https://test-dvla-api.com"


class Preview(Config):
    NOTIFY_EMAIL_DOMAIN = "notify.works"
    NOTIFY_ENVIRONMENT = "preview"
    S3_BUCKET_CSV_UPLOAD = "preview-notifications-csv-upload"
    S3_BUCKET_CONTACT_LIST = "preview-contact-list"
    S3_BUCKET_TEST_LETTERS = "preview-test-letters"
    S3_BUCKET_DVLA_RESPONSE = "notify.works-ftp"
    S3_BUCKET_LETTERS_PDF = "preview-letters-pdf"
    S3_BUCKET_LETTERS_SCAN = "preview-letters-scan"
    S3_BUCKET_INVALID_PDF = "preview-letters-invalid-pdf"
    S3_BUCKET_TRANSIENT_UPLOADED_LETTERS = "preview-transient-uploaded-letters"
    S3_BUCKET_LETTER_SANITISE = "preview-letters-sanitise"
    FROM_NUMBER = "preview"
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = False
    DVLA_API_TLS_CIPHERS = os.environ.get("DVLA_API_TLS_CIPHERS", "must-supply-tls-ciphers")


class Staging(Config):
    NOTIFY_EMAIL_DOMAIN = "staging-notify.works"
    NOTIFY_ENVIRONMENT = "staging"
    S3_BUCKET_CSV_UPLOAD = "staging-notifications-csv-upload"
    S3_BUCKET_CONTACT_LIST = "staging-contact-list"
    S3_BUCKET_TEST_LETTERS = "staging-test-letters"
    S3_BUCKET_DVLA_RESPONSE = "staging-notify.works-ftp"
    S3_BUCKET_LETTERS_PDF = "staging-letters-pdf"
    S3_BUCKET_LETTERS_SCAN = "staging-letters-scan"
    S3_BUCKET_INVALID_PDF = "staging-letters-invalid-pdf"
    S3_BUCKET_TRANSIENT_UPLOADED_LETTERS = "staging-transient-uploaded-letters"
    S3_BUCKET_LETTER_SANITISE = "staging-letters-sanitise"
    FROM_NUMBER = "stage"
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True
    DVLA_API_TLS_CIPHERS = os.environ.get("DVLA_API_TLS_CIPHERS", "must-supply-tls-ciphers")


class Production(Config):
    NOTIFY_EMAIL_DOMAIN = "notifications.service.gov.uk"
    NOTIFY_ENVIRONMENT = "production"
    S3_BUCKET_CSV_UPLOAD = "live-notifications-csv-upload"
    S3_BUCKET_CONTACT_LIST = "production-contact-list"
    S3_BUCKET_TEST_LETTERS = "production-test-letters"
    S3_BUCKET_DVLA_RESPONSE = "notifications.service.gov.uk-ftp"
    S3_BUCKET_LETTERS_PDF = "production-letters-pdf"
    S3_BUCKET_LETTERS_SCAN = "production-letters-scan"
    S3_BUCKET_INVALID_PDF = "production-letters-invalid-pdf"
    S3_BUCKET_TRANSIENT_UPLOADED_LETTERS = "production-transient-uploaded-letters"
    S3_BUCKET_LETTER_SANITISE = "production-letters-sanitise"
    FROM_NUMBER = "GOVUK"
    API_RATE_LIMIT_ENABLED = True
    CHECK_PROXY_HEADER = True
    SES_STUB_URL = None

    CRONITOR_ENABLED = True

    DVLA_API_BASE_URL = os.environ.get("DVLA_API_BASE_URL", "https://driver-vehicle-licensing.api.gov.uk")
    DVLA_API_TLS_CIPHERS = os.environ.get("DVLA_API_TLS_CIPHERS", "must-supply-tls-ciphers")


class CloudFoundryConfig(Config):
    pass


# CloudFoundry sandbox
class Sandbox(CloudFoundryConfig):
    NOTIFY_EMAIL_DOMAIN = "notify.works"
    NOTIFY_ENVIRONMENT = "sandbox"
    S3_BUCKET_CSV_UPLOAD = "cf-sandbox-notifications-csv-upload"
    S3_BUCKET_CONTACT_LIST = "cf-sandbox-contact-list"
    S3_BUCKET_LETTERS_PDF = "cf-sandbox-letters-pdf"
    S3_BUCKET_TEST_LETTERS = "cf-sandbox-test-letters"
    S3_BUCKET_DVLA_RESPONSE = "notify.works-ftp"
    S3_BUCKET_LETTERS_SCAN = "cf-sandbox-letters-scan"
    S3_BUCKET_INVALID_PDF = "cf-sandbox-letters-invalid-pdf"
    FROM_NUMBER = "sandbox"


configs = {
    "development": Development,
    "test": Test,
    "production": Production,
    "staging": Staging,
    "preview": Preview,
    "sandbox": Sandbox,
}
