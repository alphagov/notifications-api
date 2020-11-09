import os
import json

import pytest

from app.cloudfoundry_config import extract_cloudfoundry_config, set_config_env_vars


@pytest.fixture
def postgres_config():
    return [
        {
            'credentials': {
                'uri': 'postgres uri'
            }
        }
    ]


@pytest.fixture
def cloudfoundry_config(postgres_config):
    return {
        'postgres': postgres_config,
        'user-provided': []
    }


@pytest.fixture
def cloudfoundry_environ(os_environ, cloudfoundry_config):
    os.environ['VCAP_SERVICES'] = json.dumps(cloudfoundry_config)
    os.environ['VCAP_APPLICATION'] = '{"space_name": "🚀🌌"}'


@pytest.fixture
def postgres_config_with_setting():
    return [
        {
            'credentials': {
                'uri': 'postgres uri?setting=true'
            }
        }
    ]


@pytest.fixture
def cloudfoundry_config_with_setting(postgres_config_with_setting):
    return {
        'postgres': postgres_config_with_setting,
        'user-provided': []
    }


@pytest.fixture
def cloudfoundry_environ_with_setting(os_environ, cloudfoundry_config_with_setting):
    os.environ['VCAP_SERVICES'] = json.dumps(cloudfoundry_config_with_setting)
    os.environ['VCAP_APPLICATION'] = '{"space_name": "🚀🌌"}'


def test_extract_cloudfoundry_config_populates_other_vars(cloudfoundry_environ):
    extract_cloudfoundry_config()

    assert os.environ['SQLALCHEMY_DATABASE_URI'] == 'postgres uri?sslmode=verify-full'
    assert os.environ['NOTIFY_ENVIRONMENT'] == '🚀🌌'
    assert os.environ['NOTIFY_LOG_PATH'] == '/home/vcap/logs/app.log'


def test_set_config_env_vars_ignores_unknown_configs(cloudfoundry_config, cloudfoundry_environ):
    cloudfoundry_config['foo'] = {'credentials': {'foo': 'foo'}}
    cloudfoundry_config['user-provided'].append({
        'name': 'bar', 'credentials': {'bar': 'bar'}
    })

    set_config_env_vars(cloudfoundry_config)

    assert 'foo' not in os.environ
    assert 'bar' not in os.environ


def test_extract_cloudfoundry_config_populates_postgres_with_setting(cloudfoundry_environ_with_setting):
    extract_cloudfoundry_config()

    assert os.environ['SQLALCHEMY_DATABASE_URI'] == 'postgres uri?setting=true&sslmode=verify-full'
