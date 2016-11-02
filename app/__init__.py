import uuid
import os

from flask import request, url_for, g, jsonify
from flask import Flask, _request_ctx_stack
from flask.ext.sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from monotonic import monotonic
from werkzeug.local import LocalProxy
from notifications_utils import logging
from app.celery.celery import NotifyCelery
from app.clients import Clients
from app.clients.sms.mmg import MMGClient
from app.clients.sms.firetext import FiretextClient
from app.clients.sms.loadtesting import LoadtestingClient
from app.clients.email.aws_ses import AwsSesClient
from app.clients.statsd.statsd_client import StatsdClient
from app.encryption import Encryption


DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
DATE_FORMAT = "%Y-%m-%d"

db = SQLAlchemy()
ma = Marshmallow()
notify_celery = NotifyCelery()
firetext_client = FiretextClient()
loadtest_client = LoadtestingClient()
mmg_client = MMGClient()
aws_ses_client = AwsSesClient()
encryption = Encryption()
statsd_client = StatsdClient()

clients = Clients()

api_user = LocalProxy(lambda: _request_ctx_stack.top.api_user)


def create_app(app_name=None):
    application = Flask(__name__)

    from config import configs
    application.config.from_object(configs[os.environ['NOTIFY_ENVIRONMENT']])
    if app_name:
        application.config['NOTIFY_APP_NAME'] = app_name

    init_app(application)
    db.init_app(application)
    ma.init_app(application)
    statsd_client.init_app(application)
    logging.init_app(application, statsd_client)
    firetext_client.init_app(application, statsd_client=statsd_client)
    loadtest_client.init_app(application, statsd_client=statsd_client)
    mmg_client.init_app(application, statsd_client=statsd_client)
    aws_ses_client.init_app(application.config['AWS_REGION'], statsd_client=statsd_client)
    notify_celery.init_app(application)
    encryption.init_app(application)
    clients.init_app(sms_clients=[firetext_client, mmg_client, loadtest_client], email_clients=[aws_ses_client])

    register_blueprint(application)
    register_v2_blueprints(application)

    return application


def register_blueprint(application):
    from app.service.rest import service_blueprint
    from app.user.rest import user as user_blueprint
    from app.template.rest import template as template_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.job.rest import job as job_blueprint
    from app.notifications.rest import notifications as notifications_blueprint
    from app.invite.rest import invite as invite_blueprint
    from app.accept_invite.rest import accept_invite
    from app.template_statistics.rest import template_statistics as template_statistics_blueprint
    from app.events.rest import events as events_blueprint
    from app.provider_details.rest import provider_details as provider_details_blueprint
    from app.spec.rest import spec as spec_blueprint
    from app.organisation.rest import organisation_blueprint
    from app.delivery.rest import delivery_blueprint

    application.register_blueprint(service_blueprint, url_prefix='/service')
    application.register_blueprint(user_blueprint, url_prefix='/user')
    application.register_blueprint(template_blueprint)
    application.register_blueprint(status_blueprint)
    application.register_blueprint(notifications_blueprint)
    application.register_blueprint(job_blueprint)
    application.register_blueprint(invite_blueprint)
    application.register_blueprint(delivery_blueprint)
    application.register_blueprint(accept_invite, url_prefix='/invite')
    application.register_blueprint(template_statistics_blueprint)
    application.register_blueprint(events_blueprint)
    application.register_blueprint(provider_details_blueprint, url_prefix='/provider-details')
    application.register_blueprint(spec_blueprint, url_prefix='/spec')
    application.register_blueprint(organisation_blueprint, url_prefix='/organisation')


def register_v2_blueprints(application):
    from app.v2.notifications.post_notifications import notification_blueprint
    application.register_blueprint(notification_blueprint)


def init_app(app):
    @app.before_request
    def required_authentication():
        no_auth_req = [
            url_for('status.show_status'),
            url_for('notifications.process_ses_response'),
            url_for('notifications.process_firetext_response'),
            url_for('notifications.process_mmg_response'),
            url_for('status.show_delivery_status'),
            url_for('spec.get_spec')
        ]
        if request.path not in no_auth_req:
            from app.authentication import auth
            error = auth.requires_auth()
            if error:
                return error

    @app.before_request
    def record_request_details():
        g.start = monotonic()
        g.endpoint = request.endpoint

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
        return response

    @app.errorhandler(404)
    def page_not_found(e):
        msg = e.description or "Not found"
        app.logger.exception(msg)
        return jsonify(result='error', message=msg), 404


def create_uuid():
    return str(uuid.uuid4())
