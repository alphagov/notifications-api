import time
import os
import random
import string
import uuid

from celery import current_task
from flask import _request_ctx_stack, request, g, jsonify, make_response, current_app, has_request_context
from flask_sqlalchemy import SQLAlchemy as _SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate
from gds_metrics import GDSMetrics
from gds_metrics.metrics import Gauge, Histogram
from time import monotonic
from notifications_utils.clients.zendesk.zendesk_client import ZendeskClient
from notifications_utils.clients.statsd.statsd_client import StatsdClient
from notifications_utils.clients.redis.redis_client import RedisClient
from notifications_utils.clients.encryption.encryption_client import Encryption
from notifications_utils import logging, request_helper
from sqlalchemy import event
from werkzeug.exceptions import HTTPException as WerkzeugHTTPException
from werkzeug.local import LocalProxy

from app.celery.celery import NotifyCelery
from app.clients import Clients
from app.clients.cbc_proxy import CBCProxyClient, CBCProxyNoopClient
from app.clients.document_download import DocumentDownloadClient
from app.clients.email.aws_ses import AwsSesClient
from app.clients.email.aws_ses_stub import AwsSesStubClient
from app.clients.sms.firetext import FiretextClient
from app.clients.sms.mmg import MMGClient
from app.clients.performance_platform.performance_platform_client import PerformancePlatformClient

DATETIME_FORMAT_NO_TIMEZONE = "%Y-%m-%d %H:%M:%S.%f"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATE_FORMAT = "%Y-%m-%d"


class SQLAlchemy(_SQLAlchemy):
    """We need to subclass SQLAlchemy in order to override create_engine options"""

    def apply_driver_hacks(self, app, info, options):
        super().apply_driver_hacks(app, info, options)
        if 'connect_args' not in options:
            options['connect_args'] = {}
        options['connect_args']["options"] = "-c statement_timeout={}".format(
            int(app.config['SQLALCHEMY_STATEMENT_TIMEOUT']) * 1000
        )


db = SQLAlchemy()
migrate = Migrate()
ma = Marshmallow()
notify_celery = NotifyCelery()
firetext_client = FiretextClient()
mmg_client = MMGClient()
aws_ses_client = AwsSesClient()
aws_ses_stub_client = AwsSesStubClient()
encryption = Encryption()
zendesk_client = ZendeskClient()
statsd_client = StatsdClient()
redis_store = RedisClient()
performance_platform_client = PerformancePlatformClient()
cbc_proxy_client = CBCProxyNoopClient()
document_download_client = DocumentDownloadClient()
metrics = GDSMetrics()

clients = Clients()

api_user = LocalProxy(lambda: _request_ctx_stack.top.api_user)
authenticated_service = LocalProxy(lambda: _request_ctx_stack.top.authenticated_service)

CONCURRENT_REQUESTS = Gauge(
    'concurrent_web_request_count',
    'How many concurrent requests are currently being served',
)


def create_app(application):
    from app.config import configs

    notify_environment = os.environ['NOTIFY_ENVIRONMENT']

    application.config.from_object(configs[notify_environment])

    application.config['NOTIFY_APP_NAME'] = application.name
    init_app(application)

    # Metrics intentionally high up to give the most accurate timing and reliability that the metric is recorded
    metrics.init_app(application)
    request_helper.init_app(application)
    db.init_app(application)
    migrate.init_app(application, db=db)
    ma.init_app(application)
    zendesk_client.init_app(application)
    statsd_client.init_app(application)
    logging.init_app(application, statsd_client)
    firetext_client.init_app(application, statsd_client=statsd_client)
    mmg_client.init_app(application, statsd_client=statsd_client)

    aws_ses_client.init_app(application.config['AWS_REGION'], statsd_client=statsd_client)
    aws_ses_stub_client.init_app(
        application.config['AWS_REGION'],
        statsd_client=statsd_client,
        stub_url=application.config['SES_STUB_URL']
    )
    # If a stub url is provided for SES, then use the stub client rather than the real SES boto client
    email_clients = [aws_ses_stub_client] if application.config['SES_STUB_URL'] else [aws_ses_client]
    clients.init_app(sms_clients=[firetext_client, mmg_client], email_clients=email_clients)

    notify_celery.init_app(application)
    encryption.init_app(application)
    redis_store.init_app(application)
    performance_platform_client.init_app(application)
    document_download_client.init_app(application)

    global cbc_proxy_client
    if application.config['CBC_PROXY_AWS_ACCESS_KEY_ID']:
        cbc_proxy_client = CBCProxyClient()
    cbc_proxy_client.init_app(application)

    register_blueprint(application)
    register_v2_blueprints(application)

    # avoid circular imports by importing this file later
    from app.commands import setup_commands
    setup_commands(application)

    # set up sqlalchemy events
    setup_sqlalchemy_events(application)

    return application


def register_blueprint(application):
    from app.service.rest import service_blueprint
    from app.service.callback_rest import service_callback_blueprint
    from app.user.rest import user_blueprint
    from app.template.rest import template_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.job.rest import job_blueprint
    from app.notifications.rest import notifications as notifications_blueprint
    from app.invite.rest import invite as invite_blueprint
    from app.accept_invite.rest import accept_invite
    from app.template_statistics.rest import template_statistics as template_statistics_blueprint
    from app.events.rest import events as events_blueprint
    from app.provider_details.rest import provider_details as provider_details_blueprint
    from app.email_branding.rest import email_branding_blueprint
    from app.inbound_number.rest import inbound_number_blueprint
    from app.inbound_sms.rest import inbound_sms as inbound_sms_blueprint
    from app.notifications.receive_notifications import receive_notifications_blueprint
    from app.notifications.notifications_sms_callback import sms_callback_blueprint
    from app.notifications.notifications_letter_callback import letter_callback_blueprint
    from app.authentication.auth import requires_admin_auth, requires_auth, requires_no_auth
    from app.letters.rest import letter_job
    from app.billing.rest import billing_blueprint
    from app.organisation.rest import organisation_blueprint
    from app.organisation.invite_rest import organisation_invite_blueprint
    from app.complaint.complaint_rest import complaint_blueprint
    from app.platform_stats.rest import platform_stats_blueprint
    from app.template_folder.rest import template_folder_blueprint
    from app.letter_branding.letter_branding_rest import letter_branding_blueprint
    from app.upload.rest import upload_blueprint
    from app.broadcast_message.rest import broadcast_message_blueprint

    service_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_blueprint, url_prefix='/service')

    user_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(user_blueprint, url_prefix='/user')

    template_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_blueprint)

    status_blueprint.before_request(requires_no_auth)
    application.register_blueprint(status_blueprint)

    # delivery receipts
    # TODO: make sure research mode can still trigger sms callbacks, then re-enable this
    sms_callback_blueprint.before_request(requires_no_auth)
    application.register_blueprint(sms_callback_blueprint)

    # inbound sms
    receive_notifications_blueprint.before_request(requires_no_auth)
    application.register_blueprint(receive_notifications_blueprint)

    notifications_blueprint.before_request(requires_auth)
    application.register_blueprint(notifications_blueprint)

    job_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(job_blueprint)

    invite_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(invite_blueprint)

    inbound_number_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(inbound_number_blueprint)

    inbound_sms_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(inbound_sms_blueprint)

    accept_invite.before_request(requires_admin_auth)
    application.register_blueprint(accept_invite, url_prefix='/invite')

    template_statistics_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_statistics_blueprint)

    events_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(events_blueprint)

    provider_details_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(provider_details_blueprint, url_prefix='/provider-details')

    email_branding_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(email_branding_blueprint, url_prefix='/email-branding')

    letter_job.before_request(requires_admin_auth)
    application.register_blueprint(letter_job)

    letter_callback_blueprint.before_request(requires_no_auth)
    application.register_blueprint(letter_callback_blueprint)

    billing_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(billing_blueprint)

    service_callback_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_callback_blueprint)

    organisation_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(organisation_blueprint, url_prefix='/organisations')

    organisation_invite_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(organisation_invite_blueprint)

    complaint_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(complaint_blueprint)

    platform_stats_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(platform_stats_blueprint, url_prefix='/platform-stats')

    template_folder_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_folder_blueprint)

    letter_branding_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(letter_branding_blueprint)

    upload_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(upload_blueprint)

    broadcast_message_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(broadcast_message_blueprint)


def register_v2_blueprints(application):
    from app.v2.inbound_sms.get_inbound_sms import v2_inbound_sms_blueprint as get_inbound_sms
    from app.v2.notifications.post_notifications import v2_notification_blueprint as post_notifications
    from app.v2.notifications.get_notifications import v2_notification_blueprint as get_notifications
    from app.v2.template.get_template import v2_template_blueprint as get_template
    from app.v2.templates.get_templates import v2_templates_blueprint as get_templates
    from app.v2.template.post_template import v2_template_blueprint as post_template
    from app.authentication.auth import requires_auth

    post_notifications.before_request(requires_auth)
    application.register_blueprint(post_notifications)

    get_notifications.before_request(requires_auth)
    application.register_blueprint(get_notifications)

    get_templates.before_request(requires_auth)
    application.register_blueprint(get_templates)

    get_template.before_request(requires_auth)
    application.register_blueprint(get_template)

    post_template.before_request(requires_auth)
    application.register_blueprint(post_template)

    get_inbound_sms.before_request(requires_auth)
    application.register_blueprint(get_inbound_sms)


def init_app(app):

    @app.before_request
    def record_request_details():
        CONCURRENT_REQUESTS.inc()

        g.start = monotonic()
        g.endpoint = request.endpoint

    @app.after_request
    def after_request(response):
        CONCURRENT_REQUESTS.dec()

        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
        return response

    @app.errorhandler(Exception)
    def exception(error):
        app.logger.exception(error)
        # error.code is set for our exception types.
        msg = getattr(error, 'message', str(error))
        code = getattr(error, 'code', 500)
        return jsonify(result='error', message=msg), code

    @app.errorhandler(WerkzeugHTTPException)
    def werkzeug_exception(e):
        return make_response(
            jsonify(result='error', message=e.description),
            e.code,
            e.get_headers()
        )

    @app.errorhandler(404)
    def page_not_found(e):
        msg = e.description or "Not found"
        return jsonify(result='error', message=msg), 404


def create_uuid():
    return str(uuid.uuid4())


def create_random_identifier():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))


def setup_sqlalchemy_events(app):

    TOTAL_DB_CONNECTIONS = Gauge(
        'db_connection_total_connected',
        'How many db connections are currently held (potentially idle) by the server',
    )

    TOTAL_CHECKED_OUT_DB_CONNECTIONS = Gauge(
        'db_connection_total_checked_out',
        'How many db connections are currently checked out by web requests',
    )

    DB_CONNECTION_OPEN_DURATION_SECONDS = Histogram(
        'db_connection_open_duration_seconds',
        'How long db connections are held open for in seconds',
        ['method', 'host', 'path']
    )

    # need this or db.engine isn't accessible
    with app.app_context():
        @event.listens_for(db.engine, 'connect')
        def connect(dbapi_connection, connection_record):
            # connection first opened with db
            TOTAL_DB_CONNECTIONS.inc()

        @event.listens_for(db.engine, 'close')
        def close(dbapi_connection, connection_record):
            # connection closed (probably only happens with overflow connections)
            TOTAL_DB_CONNECTIONS.dec()

        @event.listens_for(db.engine, 'checkout')
        def checkout(dbapi_connection, connection_record, connection_proxy):
            try:
                # connection given to a web worker
                TOTAL_CHECKED_OUT_DB_CONNECTIONS.inc()

                # this will overwrite any previous checkout_at timestamp
                connection_record.info['checkout_at'] = time.monotonic()

                # checkin runs after the request is already torn down, therefore we add the request_data onto the
                # connection_record as otherwise it won't have that information when checkin actually runs.
                # Note: this is not a problem for checkouts as the checkout always happens within a web request or task

                # web requests
                if has_request_context():
                    connection_record.info['request_data'] = {
                        'method': request.method,
                        'host': request.host,
                        'url_rule': request.url_rule.rule if request.url_rule else 'No endpoint'
                    }
                # celery apps
                elif current_task:
                    connection_record.info['request_data'] = {
                        'method': 'celery',
                        'host': current_app.config['NOTIFY_APP_NAME'],  # worker name
                        'url_rule': current_task.name,  # task name
                    }
                # anything else. migrations possibly.
                else:
                    current_app.logger.warning('Checked out sqlalchemy connection from outside of request/task')
                    connection_record.info['request_data'] = {
                        'method': 'unknown',
                        'host': 'unknown',
                        'url_rule': 'unknown',
                    }
            except Exception:
                current_app.logger.exception("Exception caught for checkout event.")

        @event.listens_for(db.engine, 'checkin')
        def checkin(dbapi_connection, connection_record):
            try:
                # connection returned by a web worker
                TOTAL_CHECKED_OUT_DB_CONNECTIONS.dec()

                # duration that connection was held by a single web request
                duration = time.monotonic() - connection_record.info['checkout_at']

                DB_CONNECTION_OPEN_DURATION_SECONDS.labels(
                    connection_record.info['request_data']['method'],
                    connection_record.info['request_data']['host'],
                    connection_record.info['request_data']['url_rule']
                ).observe(duration)
            except Exception:
                current_app.logger.exception("Exception caught for checkin event.")
