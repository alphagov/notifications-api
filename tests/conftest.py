from contextlib import contextmanager
import os

import boto3
from unittest import mock
import pytest
from alembic.command import upgrade
from alembic.config import Config
from flask.ext.migrate import Migrate, MigrateCommand
from flask.ext.script import Manager

from app import create_app, db


@pytest.fixture(scope='session')
def notify_api(request):
    app = create_app()
    ctx = app.app_context()
    ctx.push()

    def teardown():
        ctx.pop()

    request.addfinalizer(teardown)
    return app


@pytest.fixture(scope='function')
def client(notify_api):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        yield client


@pytest.fixture(scope='session')
def notify_db(notify_api, request):
    Migrate(notify_api, db)
    Manager(db, MigrateCommand)
    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    ALEMBIC_CONFIG = os.path.join(BASE_DIR, 'migrations')
    config = Config(ALEMBIC_CONFIG + '/alembic.ini')
    config.set_main_option("script_location", ALEMBIC_CONFIG)

    with notify_api.app_context():
        upgrade(config, 'head')

    def teardown():
        db.session.remove()
        db.get_engine(notify_api).dispose()

    request.addfinalizer(teardown)
    return db


@pytest.fixture(scope='function')
def notify_db_session(request, notify_db):
    def teardown():
        notify_db.session.remove()
        for tbl in reversed(notify_db.metadata.sorted_tables):
            if tbl.name not in ["provider_details", "key_types", "branding_type", "job_status"]:
                notify_db.engine.execute(tbl.delete())
        notify_db.session.commit()

    request.addfinalizer(teardown)


@pytest.fixture(scope='function')
def os_environ(request):
    env_patch = mock.patch('os.environ', {})
    request.addfinalizer(env_patch.stop)

    return env_patch.start()


@pytest.fixture(scope='function')
def sqs_client_conn(request):
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
