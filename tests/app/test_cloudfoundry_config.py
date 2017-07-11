import os
import json

import pytest

from app.cloudfoundry_config import extract_cloudfoundry_config, set_config_env_vars


@pytest.fixture
def notify_config():
    return {
        'name': 'notify-config',
        'credentials': {
            'admin_base_url': 'admin base url',
            'api_host_name': 'api host name',
            'admin_client_secret': 'admin client secret',
            'secret_key': 'secret key',
            'dangerous_salt': 'dangerous salt',
            'performance_platform_token': 'performance platform token',
            'allow_ip_inbound_sms': ['111.111.111.111', '100.100.100.100']
        }
    }


@pytest.fixture
def aws_config():
    return {
        'name': 'notify-aws',
        'credentials': {
            'sqs_queue_prefix': 'sqs queue prefix',
            'aws_access_key_id': 'aws access key id',
            'aws_secret_access_key': 'aws secret access key',
        }
    }


@pytest.fixture
def hosted_graphite_config():
    return {
        'name': 'hosted-graphite',
        'credentials': {
            'statsd_prefix': 'statsd prefix'
        }
    }


@pytest.fixture
def mmg_config():
    return {
        'name': 'mmg',
        'credentials': {
            'api_url': 'mmg api url',
            'api_key': 'mmg api key'
        }
    }


@pytest.fixture
def firetext_config():
    return {
        'name': 'firetext',
        'credentials': {
            'api_key': 'firetext api key',
            'loadtesting_api_key': 'loadtesting api key'
        }
    }


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
def redis_config():
    return {
        'name': 'redis',
        'credentials': {
            'redis_enabled': '1',
            'redis_url': 'redis url'
        }
    }


@pytest.fixture
def cloudfoundry_config(
        postgres_config,
        notify_config,
        aws_config,
        hosted_graphite_config,
        mmg_config,
        firetext_config,
        redis_config
):
    return {
        'postgres': postgres_config,
        'user-provided': [
            notify_config,
            aws_config,
            hosted_graphite_config,
            mmg_config,
            firetext_config,
            redis_config
        ]
    }


@pytest.fixture
def cloudfoundry_environ(monkeypatch, cloudfoundry_config):
    monkeypatch.setenv('VCAP_SERVICES', json.dumps(cloudfoundry_config))
    monkeypatch.setenv('VCAP_APPLICATION', '{"space_name": "🚀🌌"}')


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_extract_cloudfoundry_config_populates_other_vars():
    extract_cloudfoundry_config()

    assert os.environ['SQLALCHEMY_DATABASE_URI'] == 'postgres uri'
    assert os.environ['LOGGING_STDOUT_JSON'] == '1'
    assert os.environ['NOTIFY_ENVIRONMENT'] == '🚀🌌'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_set_config_env_vars_ignores_unknown_configs(cloudfoundry_config):
    cloudfoundry_config['foo'] = {'credentials': {'foo': 'foo'}}
    cloudfoundry_config['user-provided'].append({
        'name': 'bar', 'credentials': {'bar': 'bar'}
    })

    set_config_env_vars(cloudfoundry_config)

    assert 'foo' not in os.environ
    assert 'bar' not in os.environ


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_notify_config():
    extract_cloudfoundry_config()

    assert os.environ['ADMIN_BASE_URL'] == 'admin base url'
    assert os.environ['API_HOST_NAME'] == 'api host name'
    assert os.environ['ADMIN_CLIENT_SECRET'] == 'admin client secret'
    assert os.environ['SECRET_KEY'] == 'secret key'
    assert os.environ['DANGEROUS_SALT'] == 'dangerous salt'
    assert os.environ['PERFORMANCE_PLATFORM_TOKEN'] == 'performance platform token'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_notify_config_if_perf_platform_not_set(cloudfoundry_config):
    del cloudfoundry_config['user-provided'][0]['credentials']['performance_platform_token']

    set_config_env_vars(cloudfoundry_config)

    assert os.environ['PERFORMANCE_PLATFORM_TOKEN'] == ''


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_aws_config():
    extract_cloudfoundry_config()

    assert os.environ['NOTIFICATION_QUEUE_PREFIX'] == 'sqs queue prefix'
    assert os.environ['AWS_ACCESS_KEY_ID'] == 'aws access key id'
    assert os.environ['AWS_SECRET_ACCESS_KEY'] == 'aws secret access key'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_hosted_graphite_config():
    extract_cloudfoundry_config()

    assert os.environ['STATSD_PREFIX'] == 'statsd prefix'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_mmg_config():
    extract_cloudfoundry_config()

    assert os.environ['MMG_URL'] == 'mmg api url'
    assert os.environ['MMG_API_KEY'] == 'mmg api key'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_firetext_config():
    extract_cloudfoundry_config()

    assert os.environ['FIRETEXT_API_KEY'] == 'firetext api key'
    assert os.environ['LOADTESTING_API_KEY'] == 'loadtesting api key'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_redis_config():
    extract_cloudfoundry_config()

    assert os.environ['REDIS_ENABLED'] == '1'
    assert os.environ['REDIS_URL'] == 'redis url'


@pytest.mark.usefixtures('os_environ', 'cloudfoundry_environ')
def test_sms_inbound_config():
    extract_cloudfoundry_config()

    assert os.environ['SMS_INBOUND_WHITELIST'] == ['111.111.111.111', '100.100.100.100']
