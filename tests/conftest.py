from contextlib import contextmanager
import os

import boto3
import pytest
from alembic.command import upgrade
from alembic.config import Config
from flask.ext.migrate import Migrate, MigrateCommand
from flask.ext.script import Manager

from app import create_app, db


@pytest.fixture(scope='session')
def notify_api():
    app = create_app()

    # deattach server-error error handlers - error_handler_spec looks like:
    #   {'blueprint_name': {
    #       status_code: [error_handlers],
    #       None: [ tuples of (exception, )]
    # }}
    for error_handlers in app.error_handler_spec.values():
        error_handlers.pop(500, None)
        if None in error_handlers:
            error_handlers[None] = [
                exception_handler
                for exception_handler in error_handlers[None]
                if exception_handler[0] != Exception
            ]
            if error_handlers[None] == []:
                error_handlers.pop(None)

    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()


@pytest.fixture(scope='function')
def client(notify_api):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        yield client


@pytest.fixture(scope='session')
def notify_db(notify_api):
    assert db.engine.url.database != 'notification_api', 'dont run tests against main db'
    Migrate(notify_api, db)
    Manager(db, MigrateCommand)
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    ALEMBIC_CONFIG = os.path.join(BASE_DIR, 'migrations')
    config = Config(ALEMBIC_CONFIG + '/alembic.ini')
    config.set_main_option("script_location", ALEMBIC_CONFIG)

    with notify_api.app_context():
        upgrade(config, 'head')

    yield db

    db.session.remove()
    db.get_engine(notify_api).dispose()


@pytest.fixture(scope='function')
def notify_db_session(notify_db):
    yield notify_db

    notify_db.session.remove()
    for tbl in reversed(notify_db.metadata.sorted_tables):
        if tbl.name not in ["provider_details",
                            "key_types",
                            "branding_type",
                            "job_status",
                            "provider_details_history",
                            "template_process_type",
                            "dvla_organisation",
                            "rates"]:
            notify_db.engine.execute(tbl.delete())
    notify_db.session.commit()


@pytest.fixture
def os_environ():
    """
    clear os.environ, and restore it after the test runs
    """
    # for use whenever you expect code to edit environment variables
    old_env = os.environ.copy()
    os.environ = {}
    yield
    os.environ = old_env


@pytest.fixture(scope='function')
def sqs_client_conn():
    boto3.setup_default_session(region_name='eu-west-1')
    return boto3.resource('sqs')


def pytest_generate_tests(metafunc):
    # Copied from https://gist.github.com/pfctdayelise/5719730
    idparametrize = getattr(metafunc.function, 'idparametrize', None)
    if idparametrize:
        argnames, testdata = idparametrize.args
        ids, argvalues = zip(*sorted(testdata.items()))
        metafunc.parametrize(argnames, argvalues, ids=ids)


@contextmanager
def set_config(app, name, value):
    old_val = app.config.get(name)
    app.config[name] = value
    yield
    app.config[name] = old_val


@contextmanager
def set_config_values(app, dict):
    old_values = {}

    for key in dict:
        old_values[key] = app.config.get(key)
        app.config[key] = dict[key]

    yield

    for key in dict:
        app.config[key] = old_values[key]
