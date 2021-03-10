import importlib
import os
from unittest import mock

import pytest

from app import config
from app.config import QueueNames


def cf_conf():
    os.environ['ADMIN_BASE_URL'] = 'cf'


@pytest.fixture
def reload_config():
    """
    Reset config, by simply re-running config.py from a fresh environment
    """
    old_env = os.environ.copy()

    yield

    os.environ.clear()
    for k, v in old_env.items():
        os.environ[k] = v

    importlib.reload(config)


def test_load_cloudfoundry_config_if_available(reload_config):
    os.environ['ADMIN_BASE_URL'] = 'env'
    os.environ['VCAP_SERVICES'] = 'some json blob'
    os.environ['VCAP_APPLICATION'] = 'some json blob'

    with mock.patch('app.cloudfoundry_config.extract_cloudfoundry_config', side_effect=cf_conf) as cf_config:
        # reload config so that its module level code (ie: all of it) is re-instantiated
        importlib.reload(config)

    assert cf_config.called

    assert os.environ['ADMIN_BASE_URL'] == 'cf'
    assert config.Config.ADMIN_BASE_URL == 'cf'


def test_load_config_if_cloudfoundry_not_available(reload_config):
    os.environ['ADMIN_BASE_URL'] = 'env'
    os.environ.pop('VCAP_SERVICES', None)

    with mock.patch('app.cloudfoundry_config.extract_cloudfoundry_config') as cf_config:
        # reload config so that its module level code (ie: all of it) is re-instantiated
        importlib.reload(config)

    assert not cf_config.called

    assert os.environ['ADMIN_BASE_URL'] == 'env'
    assert config.Config.ADMIN_BASE_URL == 'env'


def test_queue_names_all_queues_correct():
    # Need to ensure that all_queues() only returns queue names used in API
    queues = QueueNames.all_queues()
    assert len(queues) == 18
    assert set([
        QueueNames.PRIORITY,
        QueueNames.PERIODIC,
        QueueNames.DATABASE,
        QueueNames.SEND_SMS,
        QueueNames.SEND_EMAIL,
        QueueNames.RESEARCH_MODE,
        QueueNames.REPORTING,
        QueueNames.JOBS,
        QueueNames.RETRY,
        QueueNames.NOTIFY,
        QueueNames.CREATE_LETTERS_PDF,
        QueueNames.CALLBACKS,
        QueueNames.CALLBACKS_RETRY,
        QueueNames.LETTERS,
        QueueNames.SMS_CALLBACKS,
        QueueNames.SAVE_API_EMAIL,
        QueueNames.SAVE_API_SMS,
        QueueNames.BROADCASTS,
    ]) == set(queues)
