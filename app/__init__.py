import os
import re
import ast

from flask import request, url_for
from flask._compat import string_types
from flask import Flask, _request_ctx_stack
from flask.ext.sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from werkzeug.local import LocalProxy
from config import configs
from utils import logging
from notify_client import NotifyAPIClient
from app.celery.celery import NotifyCelery


db = SQLAlchemy()
ma = Marshmallow()
notify_alpha_client = NotifyAPIClient()
celery = NotifyCelery()
api_user = LocalProxy(lambda: _request_ctx_stack.top.api_user)


def create_app(config_name, config_overrides=None):
    application = Flask(__name__)

    application.config['NOTIFY_API_ENVIRONMENT'] = config_name
    application.config.from_object(configs[config_name])

    db.init_app(application)
    ma.init_app(application)
    init_app(application, config_overrides)
    logging.init_app(application)
    notify_alpha_client.init_app(application)

    celery.init_app(application)

    from app.service.rest import service as service_blueprint
    from app.user.rest import user as user_blueprint
    from app.template.rest import template as template_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.job.rest import job as job_blueprint
    from app.notifications.rest import notifications as notifications_blueprint

    application.register_blueprint(service_blueprint, url_prefix='/service')
    application.register_blueprint(user_blueprint, url_prefix='/user')
    application.register_blueprint(template_blueprint, url_prefix="/template")
    application.register_blueprint(status_blueprint, url_prefix='/status')
    application.register_blueprint(notifications_blueprint, url_prefix='/notifications')
    application.register_blueprint(job_blueprint)

    return application


def init_app(app, config_overrides):
    for key, value in app.config.items():
        if key in os.environ:
            app.config[key] = convert_to_boolean(os.environ[key])

    if config_overrides:
        for key in app.config.keys():
            if key in config_overrides:
                    app.config[key] = config_overrides[key]

    @app.before_request
    def required_authentication():
        if request.path != url_for('status.show_status'):
            from app.authentication import auth
            error = auth.requires_auth()
            if error:
                return error

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
        return response



def convert_to_boolean(value):
    """Turn strings to bools if they look like them

    Truthy things should be True
    >>> for truthy in ['true', 'on', 'yes', '1']:
    ...   assert convert_to_boolean(truthy) == True

    Falsey things should be False
    >>> for falsey in ['false', 'off', 'no', '0']:
    ...   assert convert_to_boolean(falsey) == False

    Other things should be unchanged
    >>> for value in ['falsey', 'other', True, 0]:
    ...   assert convert_to_boolean(value) == value
    """
    if isinstance(value, string_types):
        if value.lower() in ['t', 'true', 'on', 'yes', '1']:
            return True
        elif value.lower() in ['f', 'false', 'off', 'no', '0']:
            return False

    return value


def convert_to_number(value):
    """Turns numeric looking things into floats or ints

    Integery things should be integers
    >>> for inty in ['0', '1', '2', '99999']:
    ...   assert isinstance(convert_to_number(inty), int)

    Floaty things should be floats
    >>> for floaty in ['0.99', '1.1', '1000.0000001']:
    ...   assert isinstance(convert_to_number(floaty), float)

    Other things should be unchanged
    >>> for value in [0, 'other', True, 123]:
    ...   assert convert_to_number(value) == value
    """
    try:
        return float(value) if "." in value else int(value)
    except (TypeError, ValueError):
        return value


def get_api_version():
    build = 'n/a'
    build_time = "n/a"
    try:
        from app import version
        build = version.__build__
        build_time = version.__time__
    except:
        pass
    return build, build_time


def get_db_version():
    try:
        query = 'SELECT version_num FROM alembic_version'
        full_name = db.session.execute(query).fetchone()[0]
        return full_name.split('_')[0]
    except:
        return 'n/a'
