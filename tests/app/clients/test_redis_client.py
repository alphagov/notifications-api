import pytest
from unittest.mock import Mock

from app.clients.redis.redis_client import RedisClient


@pytest.fixture(scope='function')
def enabled_redis_client(notify_api):
    notify_api.config['REDIS_ENABLED'] = True

    redis_client = RedisClient()
    redis_client.init_app(notify_api)
    redis_client.redis_store = Mock()
    return redis_client


@pytest.fixture(scope='function')
def disabled_redis_client(notify_api):
    notify_api.config['REDIS_ENABLED'] = False

    redis_client = RedisClient()
    redis_client.init_app(notify_api)
    redis_client.redis_store = Mock()
    return redis_client


def test_should_not_call_set_if_not_enabled(disabled_redis_client):
    disabled_redis_client.set('key', 'value')
    disabled_redis_client.redis_store.set.assert_not_called()


def test_should_call_set_if_enabled(enabled_redis_client):
    enabled_redis_client.set('key', 'value')
    enabled_redis_client.redis_store.set.assert_called_with('key', 'value')


def test_should_not_call_get_if_not_enabled(disabled_redis_client):
    disabled_redis_client.set('key', 'value')
    disabled_redis_client.redis_store.get.assert_not_called()


def test_should_call_get_if_enabled(enabled_redis_client):
    enabled_redis_client.get('key')
    enabled_redis_client.redis_store.get.assert_called_with('key')