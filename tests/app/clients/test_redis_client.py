import pytest
from unittest.mock import Mock

from app.clients.redis.redis_client import RedisClient
from app.clients.redis import cache_key
from freezegun import freeze_time


@pytest.fixture(scope='function')
def enabled_redis_client(notify_api, mocker):
    notify_api.config['REDIS_ENABLED'] = True
    return build_redis_client(notify_api, mocker)


@pytest.fixture(scope='function')
def disabled_redis_client(notify_api, mocker):
    notify_api.config['REDIS_ENABLED'] = False
    return build_redis_client(notify_api, mocker)


def build_redis_client(notify_api, mocker):
    redis_client = RedisClient()
    redis_client.init_app(notify_api)
    mocker.patch.object(redis_client.redis_store, 'get', return_value=100)
    mocker.patch.object(redis_client.redis_store, 'set')
    return redis_client


def test_should_not_raise_exception_if_raise_set_to_false(notify_api):
    notify_api.config['REDIS_ENABLED'] = True
    redis_client = RedisClient()
    redis_client.init_app(notify_api)
    redis_client.redis_store.get = Mock(side_effect=Exception())
    redis_client.redis_store.set = Mock(side_effect=Exception())
    redis_client.redis_store.incr = Mock(side_effect=Exception())
    assert redis_client.get('test') is None
    assert redis_client.set('test', 'test') is None
    assert redis_client.incr('test') is None


def test_should_raise_exception_if_raise_set_to_true(notify_api):
    notify_api.config['REDIS_ENABLED'] = True
    redis_client = RedisClient()
    redis_client.init_app(notify_api)
    redis_client.redis_store.get = Mock(side_effect=Exception('get failed'))
    redis_client.redis_store.set = Mock(side_effect=Exception('set failed'))
    redis_client.redis_store.incr = Mock(side_effect=Exception('inc failed'))
    with pytest.raises(Exception) as e:
        redis_client.get('test', raise_exception=True)
    assert str(e.value) == 'get failed'
    with pytest.raises(Exception) as e:
        redis_client.set('test', 'test', raise_exception=True)
    assert str(e.value) == 'set failed'
    with pytest.raises(Exception) as e:
        redis_client.incr('test', raise_exception=True)
    assert str(e.value) == 'inc failed'


def test_should_not_call_set_if_not_enabled(disabled_redis_client):
    assert not disabled_redis_client.set('key', 'value')
    disabled_redis_client.redis_store.set.assert_not_called()


def test_should_call_set_if_enabled(enabled_redis_client):
    enabled_redis_client.set('key', 'value')
    enabled_redis_client.redis_store.set.assert_called_with('key', 'value', None, None, False, False)


def test_should_not_call_get_if_not_enabled(disabled_redis_client):
    disabled_redis_client.set('key', 'value')
    disabled_redis_client.redis_store.get.assert_not_called()


def test_should_call_get_if_enabled(enabled_redis_client):
    assert enabled_redis_client.get('key') == 100
    enabled_redis_client.redis_store.get.assert_called_with('key')


def test_should_build_cache_key_service_and_action(sample_service):
    with freeze_time("2016-01-01 12:00:00.000000"):
        assert cache_key(sample_service.id) == '{}-2016-01-01-count'.format(sample_service.id)
