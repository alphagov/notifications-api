import uuid
from datetime import datetime
from unittest.mock import Mock, call, ANY

import pytest
from flask import current_app
from freezegun import freeze_time

from tests.app.db import (
    create_notification,
    create_template,
)


def set_up_get_all_from_hash(mock_redis, side_effect):
    """
    redis returns binary strings for both keys and values - so given a list of side effects (return values),
    make sure
    """
    assert type(side_effect) == list
    side_effects = []
    for ret_val in side_effect:
        if ret_val is None:
            side_effects.append(None)
        else:
            side_effects += [{str(k).encode('utf-8'): str(v).encode('utf-8') for k, v in ret_val.items()}]

    mock_redis.get_all_from_hash.side_effect = side_effects

# get_template_statistics_for_service_by_day


@pytest.mark.parametrize('query_string', [
    {},
    {'whole_days': -1},
    {'whole_days': 8},
    {'whole_days': 3.5},
    {'whole_days': 'blurk'},
])
def test_get_template_statistics_for_service_by_day_with_bad_arg_returns_400(admin_request, query_string):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=uuid.uuid4(),
        **query_string,
        _expected_status=400
    )
    assert json_resp['result'] == 'error'
    assert 'whole_days' in json_resp['message']


def test_get_template_statistics_for_service_by_day_returns_template_info(admin_request, mocker, sample_notification):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_notification.service_id,
        whole_days=1
    )

    assert len(json_resp['data']) == 1

    assert json_resp['data'][0]['count'] == 1
    assert json_resp['data'][0]['template_id'] == str(sample_notification.template_id)
    assert json_resp['data'][0]['template_name'] == 'Template Name'
    assert json_resp['data'][0]['template_type'] == 'sms'
    assert json_resp['data'][0]['is_precompiled_letter'] is False


@pytest.mark.parametrize('var_name', ['limit_days', 'whole_days'])
def test_get_template_statistics_for_service_by_day_accepts_old_query_string(
    admin_request,
    mocker,
    sample_notification,
    var_name
):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_notification.service_id,
        **{var_name: 1}
    )

    assert len(json_resp['data']) == 1


@freeze_time('2018-01-01 12:00:00')
def test_get_template_statistics_for_service_by_day_gets_out_of_redis_if_available(
    admin_request,
    mocker,
    sample_template
):
    mock_redis = mocker.patch('app.template_statistics.rest.redis_store')
    set_up_get_all_from_hash(mock_redis, [
        {sample_template.id: 3}
    ])

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_template.service_id,
        whole_days=0
    )

    assert len(json_resp['data']) == 1
    assert json_resp['data'][0]['count'] == 3
    assert json_resp['data'][0]['template_id'] == str(sample_template.id)
    mock_redis.get_all_from_hash.assert_called_once_with(
        'service-{}-template-usage-{}'.format(sample_template.service_id, '2018-01-01')
    )


@freeze_time('2018-01-02 12:00:00')
def test_get_template_statistics_for_service_by_day_goes_to_db_if_not_in_redis(
    admin_request,
    mocker,
    sample_template
):
    mock_redis = mocker.patch('app.template_statistics.rest.redis_store')

    # first time it is called redis returns data, second time returns none
    set_up_get_all_from_hash(mock_redis, [
        {sample_template.id: 2},
        None
    ])
    mock_dao = mocker.patch(
        'app.template_statistics.rest.dao_get_template_usage',
        return_value=[
            Mock(id=sample_template.id, count=3)
        ]
    )

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_template.service_id,
        whole_days=1
    )

    assert len(json_resp['data']) == 1
    assert json_resp['data'][0]['count'] == 5
    assert json_resp['data'][0]['template_id'] == str(sample_template.id)
    # first redis call
    assert mock_redis.get_all_from_hash.mock_calls == [
        call('service-{}-template-usage-{}'.format(sample_template.service_id, '2018-01-01')),
        call('service-{}-template-usage-{}'.format(sample_template.service_id, '2018-01-02'))
    ]
    # dao only called for 2nd, since redis returned values for first call
    mock_dao.assert_called_once_with(
        str(sample_template.service_id), day=datetime(2018, 1, 2)
    )
    mock_redis.set_hash_and_expire.assert_called_once_with(
        'service-{}-template-usage-{}'.format(sample_template.service_id, '2018-01-02'),
        # sets the data that the dao returned
        {str(sample_template.id): 3},
        current_app.config['EXPIRE_CACHE_EIGHT_DAYS']
    )


def test_get_template_statistics_for_service_by_day_combines_templates_correctly(
    admin_request,
    mocker,
    sample_service
):
    t1 = create_template(sample_service, template_name='1')
    t2 = create_template(sample_service, template_name='2')
    t3 = create_template(sample_service, template_name='3')  # noqa
    mock_redis = mocker.patch('app.template_statistics.rest.redis_store')

    # first time it is called redis returns data, second time returns none
    set_up_get_all_from_hash(mock_redis, [
        {t1.id: 2},
        None,
        {t1.id: 1, t2.id: 4},
    ])
    mock_dao = mocker.patch(
        'app.template_statistics.rest.dao_get_template_usage',
        return_value=[
            Mock(id=t1.id, count=8)
        ]
    )

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_service.id,
        whole_days=2
    )

    assert len(json_resp['data']) == 2
    assert json_resp['data'][0]['template_id'] == str(t1.id)
    assert json_resp['data'][0]['count'] == 11
    assert json_resp['data'][1]['template_id'] == str(t2.id)
    assert json_resp['data'][1]['count'] == 4

    assert mock_redis.get_all_from_hash.call_count == 3
    # dao only called for 2nd day
    assert mock_dao.call_count == 1


@freeze_time('2018-03-28 00:00:00')
def test_get_template_statistics_for_service_by_day_gets_stats_for_correct_days(
    admin_request,
    mocker,
    sample_template
):
    mock_redis = mocker.patch('app.template_statistics.rest.redis_store')

    # first time it is called redis returns data, second time returns none
    set_up_get_all_from_hash(mock_redis, [
        {sample_template.id: 1},  # last weds
        None,
        {sample_template.id: 1},
        {sample_template.id: 1},
        {sample_template.id: 1},
        {sample_template.id: 1},
        None,
        None,  # current day
    ])
    mock_dao = mocker.patch(
        'app.template_statistics.rest.dao_get_template_usage',
        return_value=[
            Mock(id=sample_template.id, count=2)
        ]
    )

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_template.service_id,
        whole_days=7
    )

    assert len(json_resp['data']) == 1
    assert json_resp['data'][0]['count'] == 11
    assert json_resp['data'][0]['template_id'] == str(sample_template.id)

    assert mock_redis.get_all_from_hash.call_count == 8

    assert '2018-03-21' in mock_redis.get_all_from_hash.mock_calls[0][1][0]  # last wednesday
    assert '2018-03-22' in mock_redis.get_all_from_hash.mock_calls[1][1][0]
    assert '2018-03-23' in mock_redis.get_all_from_hash.mock_calls[2][1][0]
    assert '2018-03-24' in mock_redis.get_all_from_hash.mock_calls[3][1][0]
    assert '2018-03-25' in mock_redis.get_all_from_hash.mock_calls[4][1][0]
    assert '2018-03-26' in mock_redis.get_all_from_hash.mock_calls[5][1][0]
    assert '2018-03-27' in mock_redis.get_all_from_hash.mock_calls[6][1][0]
    assert '2018-03-28' in mock_redis.get_all_from_hash.mock_calls[7][1][0]  # current day (wednesday)

    mock_dao.mock_calls == [
        call(ANY, day=datetime(2018, 3, 22)),
        call(ANY, day=datetime(2018, 3, 27)),
        call(ANY, day=datetime(2018, 3, 28))
    ]


def test_get_template_statistics_for_service_by_day_returns_empty_list_if_no_templates(
    admin_request,
    mocker,
    sample_service
):
    mock_redis = mocker.patch('app.template_statistics.rest.redis_store')

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_service.id,
        whole_days=7
    )

    assert len(json_resp['data']) == 0
    assert mock_redis.get_all_from_hash.call_count == 8
    # make sure we don't try and set any empty hashes in redis
    assert mock_redis.set_hash_and_expire.call_count == 0

# get_template_statistics_for_template


def test_get_template_statistics_for_template_returns_last_notification(admin_request, sample_template):
    create_notification(sample_template)
    create_notification(sample_template)
    notification_3 = create_notification(sample_template)

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_template_id',
        service_id=notification_3.service_id,
        template_id=notification_3.template_id
    )

    assert json_resp['data']['id'] == str(notification_3.id)


def test_get_template_statistics_for_template_returns_empty_if_no_statistics(
    admin_request,
    sample_template,
):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_template_id',
        service_id=sample_template.service_id,
        template_id=sample_template.id
    )

    assert not json_resp['data']


def test_get_template_statistics_for_template_raises_error_for_nonexistent_template(
    admin_request,
    sample_service,
    fake_uuid
):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_template_id',
        service_id=sample_service.id,
        template_id=fake_uuid,
        _expected_status=404
    )

    assert json_resp['message'] == 'No result found'
    assert json_resp['result'] == 'error'


def test_get_template_statistics_for_template_returns_empty_for_old_notification(
    admin_request,
    sample_notification_history
):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_template_id',
        service_id=sample_notification_history.service_id,
        template_id=sample_notification_history.template_id
    )

    assert not json_resp['data']
