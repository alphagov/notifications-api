from datetime import datetime

from freezegun import freeze_time
import pytest

from app.commands import populate_redis_template_usage

from tests.conftest import set_config
from tests.app.db import create_notification, create_template, create_service


def test_populate_redis_template_usage_does_nothing_if_redis_disabled(mocker, notify_api, sample_service):
    mock_redis = mocker.patch('app.commands.redis_store')
    with set_config(notify_api, 'REDIS_ENABLED', False):
        with pytest.raises(AssertionError):
            populate_redis_template_usage.callback.__wrapped__(sample_service.id, datetime.utcnow())

    assert not mock_redis.called


def test_populate_redis_template_usage_does_nothing_if_no_data(mocker, notify_api, sample_service):
    mock_redis = mocker.patch('app.commands.redis_store')
    with set_config(notify_api, 'REDIS_ENABLED', True):
        populate_redis_template_usage.callback.__wrapped__(sample_service.id, datetime.utcnow())

    assert not mock_redis.called


@freeze_time('2017-06-12')
def test_populate_redis_template_usage_only_populates_for_today(mocker, notify_api, sample_template):
    mock_redis = mocker.patch('app.commands.redis_store')
    # created at in utc
    create_notification(sample_template, created_at=datetime(2017, 6, 9, 23, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 9, 23, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 10, 0, 0, 0))
    create_notification(sample_template, created_at=datetime(2017, 6, 10, 23, 0, 0))  # actually on 11th BST

    with set_config(notify_api, 'REDIS_ENABLED', True):
        populate_redis_template_usage.callback.__wrapped__(sample_template.service_id, datetime(2017, 6, 10))

    mock_redis.set_hash_and_expire.assert_called_once_with(
        'service-{}-template-usage-2017-06-10'.format(sample_template.service_id),
        {str(sample_template.id): 3},
        notify_api.config['EXPIRE_CACHE_EIGHT_DAYS']
    )


@freeze_time('2017-06-12')
def test_populate_redis_template_usage_only_populates_for_given_service(mocker, notify_api, notify_db_session):
    mock_redis = mocker.patch('app.commands.redis_store')
    # created at in utc
    s1 = create_service(service_name='a')
    s2 = create_service(service_name='b')
    t1 = create_template(s1)
    t2 = create_template(s2)

    create_notification(t1, created_at=datetime(2017, 6, 10))
    create_notification(t1, created_at=datetime(2017, 6, 10))

    create_notification(t2, created_at=datetime(2017, 6, 10))

    with set_config(notify_api, 'REDIS_ENABLED', True):
        populate_redis_template_usage.callback.__wrapped__(s1.id, datetime(2017, 6, 10))

    mock_redis.set_hash_and_expire.assert_called_once_with(
        'service-{}-template-usage-2017-06-10'.format(s1.id),
        {str(t1.id): 2},
        notify_api.config['EXPIRE_CACHE_EIGHT_DAYS']
    )
