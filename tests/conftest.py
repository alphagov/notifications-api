import pytest
import mock
import os
from config import configs
from alembic.command import upgrade
from alembic.config import Config
from flask.ext.migrate import Migrate, MigrateCommand
from flask.ext.script import Manager

from app import create_app, db


@pytest.fixture(scope='session')
def notify_api(request):
    app = create_app('test')
    ctx = app.app_context()
    ctx.push()

    def teardown():
        ctx.pop()

    request.addfinalizer(teardown)
    return app


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
        db.drop_all()
        db.engine.execute("drop table alembic_version")
        db.get_engine(notify_api).dispose()

    request.addfinalizer(teardown)


@pytest.fixture(scope='function')
def notify_config(notify_api):
    notify_api.config['NOTIFY_API_ENVIRONMENT'] = 'test'
    notify_api.config.from_object(configs['test'])


@pytest.fixture(scope='function')
def os_environ(request):
    env_patch = mock.patch('os.environ', {})
    request.addfinalizer(env_patch.stop)

    return env_patch.start()
