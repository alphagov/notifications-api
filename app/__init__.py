import os

from flask import request, url_for
from flask import Flask, _request_ctx_stack
from flask.ext.sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from werkzeug.local import LocalProxy
from utils import logging


db = SQLAlchemy()
ma = Marshmallow()

api_user = LocalProxy(lambda: _request_ctx_stack.top.api_user)


def create_app():
    application = Flask(__name__)

    application.config.from_object(os.environ['NOTIFY_API_ENVIRONMENT'])

    db.init_app(application)
    ma.init_app(application)
    init_app(application)
    logging.init_app(application)

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


def init_app(app):
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
