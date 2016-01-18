import os

from flask._compat import string_types
from flask import Flask, _request_ctx_stack
from flask.ext.sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from werkzeug.local import LocalProxy
from config import configs
from utils import logging


db = SQLAlchemy()
ma = Marshmallow()

api_user = LocalProxy(lambda: _request_ctx_stack.top.api_user)


def create_app(config_name):
    application = Flask(__name__)

    application.config['NOTIFY_API_ENVIRONMENT'] = config_name
    application.config.from_object(configs[config_name])

    db.init_app(application)
    ma.init_app(application)
    init_app(application)
    logging.init_app(application)

    from app.service.rest import service as service_blueprint
    from app.user.rest import user as user_blueprint
    from app.template.rest import template as template_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.job.rest import job as job_blueprint

    application.register_blueprint(service_blueprint, url_prefix='/service')
    application.register_blueprint(user_blueprint, url_prefix='/user')
    application.register_blueprint(template_blueprint, url_prefix="/template")
    application.register_blueprint(status_blueprint, url_prefix='/status')
    application.register_blueprint(job_blueprint)

    return application


def init_app(app):
    for key, value in app.config.items():
        if key in os.environ:
            app.config[key] = convert_to_boolean(os.environ[key])

    @app.before_request
    def required_authentication():
        from app.authentication import auth
        error = auth.requires_auth()
        if error:
            return error


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
