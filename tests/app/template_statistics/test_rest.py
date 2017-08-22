from datetime import datetime, timedelta
import json

import pytest
from freezegun import freeze_time

from tests import create_authorization_header
from tests.app.conftest import (
    sample_template as create_sample_template,
    sample_notification,
    sample_notification_history,
    sample_email_template
)


def test_get_all_template_statistics_with_bad_arg_returns_400(client, sample_service):
    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        query_string={'limit_days': 'blurk'}
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == {'limit_days': ['blurk is not an integer']}


@freeze_time('2016-08-18')
def test_get_template_statistics_for_service(notify_db, notify_db_session, client, mocker):
    email, sms = set_up_notifications(notify_db, notify_db_session)

    mocked_redis = mocker.patch('app.redis_store.get_all_from_hash')

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics'.format(email.service_id),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 2
    assert json_resp['data'][0]['count'] == 3
    assert json_resp['data'][0]['template_id'] == str(email.id)
    assert json_resp['data'][0]['template_name'] == email.name
    assert json_resp['data'][0]['template_type'] == email.template_type
    assert json_resp['data'][1]['count'] == 3
    assert json_resp['data'][1]['template_id'] == str(sms.id)
    assert json_resp['data'][1]['template_name'] == sms.name
    assert json_resp['data'][1]['template_type'] == sms.template_type

    mocked_redis.assert_not_called()


@freeze_time('2016-08-18')
def test_get_template_statistics_for_service_limited_1_day(notify_db, notify_db_session, client,
                                                           mocker):
    email, sms = set_up_notifications(notify_db, notify_db_session)
    mock_redis = mocker.patch('app.redis_store.get_all_from_hash')

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics'.format(email.service_id),
        headers=[('Content-Type', 'application/json'), auth_header],
        query_string={'limit_days': 1}
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))['data']
    assert len(json_resp) == 2

    assert json_resp[0]['count'] == 1
    assert json_resp[0]['template_id'] == str(email.id)
    assert json_resp[0]['template_name'] == email.name
    assert json_resp[0]['template_type'] == email.template_type
    assert json_resp[1]['count'] == 1
    assert json_resp[1]['template_id'] == str(sms.id)
    assert json_resp[1]['template_name'] == sms.name
    assert json_resp[1]['template_type'] == sms.template_type

    mock_redis.assert_not_called()


@pytest.mark.parametrize("cache_values", [False, True])
@freeze_time('2016-08-18')
def test_get_template_statistics_for_service_limit_7_days(notify_db, notify_db_session, client,
                                                          mocker,
                                                          cache_values):
    email, sms = set_up_notifications(notify_db, notify_db_session)
    mock_cache_values = {str.encode(str(sms.id)): str.encode('3'),
                         str.encode(str(email.id)): str.encode('3')} if cache_values else None
    mocked_redis_get = mocker.patch('app.redis_store.get_all_from_hash', return_value=mock_cache_values)
    mocked_redis_set = mocker.patch('app.redis_store.set_hash_and_expire')

    auth_header = create_authorization_header()
    response_for_a_week = client.get(
        '/service/{}/template-statistics'.format(email.service_id),
        headers=[('Content-Type', 'application/json'), auth_header],
        query_string={'limit_days': 7}
    )

    assert response_for_a_week.status_code == 200
    json_resp = json.loads(response_for_a_week.get_data(as_text=True))
    assert len(json_resp['data']) == 2
    assert json_resp['data'][0]['count'] == 3
    assert json_resp['data'][0]['template_name'] == 'Email Template Name'
    assert json_resp['data'][1]['count'] == 3
    assert json_resp['data'][1]['template_name'] == 'Template Name'

    mocked_redis_get.assert_called_once_with("{}-template-counter-limit-7-days".format(email.service_id))
    if cache_values:
        mocked_redis_set.assert_not_called()
    else:
        mocked_redis_set.assert_called_once_with("{}-template-counter-limit-7-days".format(email.service_id),
                                                 {sms.id: 3, email.id: 3}, 600)


@freeze_time('2016-08-18')
def test_get_template_statistics_for_service_limit_30_days(notify_db, notify_db_session, client,
                                                           mocker):
    email, sms = set_up_notifications(notify_db, notify_db_session)
    mock_redis = mocker.patch('app.redis_store.get_all_from_hash')

    auth_header = create_authorization_header()

    response_for_a_month = client.get(
        '/service/{}/template-statistics'.format(email.service_id),
        headers=[('Content-Type', 'application/json'), auth_header],
        query_string={'limit_days': 30}
    )

    assert response_for_a_month.status_code == 200
    json_resp = json.loads(response_for_a_month.get_data(as_text=True))
    assert len(json_resp['data']) == 2
    assert json_resp['data'][0]['count'] == 3
    assert json_resp['data'][0]['template_name'] == 'Email Template Name'
    assert json_resp['data'][1]['count'] == 3
    assert json_resp['data'][1]['template_name'] == 'Template Name'

    mock_redis.assert_not_called()


@freeze_time('2016-08-18')
def test_get_template_statistics_for_service_no_limit(notify_db, notify_db_session, client,
                                                      mocker):
    email, sms = set_up_notifications(notify_db, notify_db_session)
    mock_redis = mocker.patch('app.redis_store.get_all_from_hash')
    auth_header = create_authorization_header()
    response_for_all = client.get(
        '/service/{}/template-statistics'.format(email.service_id),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response_for_all.status_code == 200
    json_resp = json.loads(response_for_all.get_data(as_text=True))
    assert len(json_resp['data']) == 2
    assert json_resp['data'][0]['count'] == 3
    assert json_resp['data'][0]['template_name'] == 'Email Template Name'
    assert json_resp['data'][1]['count'] == 3
    assert json_resp['data'][1]['template_name'] == 'Template Name'

    mock_redis.assert_not_called()


def set_up_notifications(notify_db, notify_db_session):
    sms = create_sample_template(notify_db, notify_db_session)
    email = sample_email_template(notify_db, notify_db_session)
    today = datetime.now()
    a_week_ago = datetime.now() - timedelta(days=7)
    a_month_ago = datetime.now() - timedelta(days=30)
    sample_notification(notify_db, notify_db_session, created_at=today, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=today, template=email)
    sample_notification(notify_db, notify_db_session, created_at=a_week_ago, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=a_week_ago, template=email)
    sample_notification(notify_db, notify_db_session, created_at=a_month_ago, template=sms)
    sample_notification(notify_db, notify_db_session, created_at=a_month_ago, template=email)
    return email, sms


@freeze_time('2016-08-18')
def test_returns_empty_list_if_no_templates_used(client, sample_service):
    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 0


def test_get_template_statistics_by_id_returns_last_notification(
        notify_db,
        notify_db_session,
        client):
    sample_notification(notify_db, notify_db_session)
    sample_notification(notify_db, notify_db_session)
    notification_3 = sample_notification(notify_db, notify_db_session)

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics/{}'.format(notification_3.service_id, notification_3.template_id),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))['data']
    assert json_resp['id'] == str(notification_3.id)


def test_get_template_statistics_for_template_returns_empty_if_no_statistics(
    client,
    sample_template,
):
    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics/{}'.format(sample_template.service_id, sample_template.id),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert not json_resp['data']


def test_get_template_statistics_raises_error_for_nonexistent_template(
    client,
    sample_service,
    fake_uuid
):
    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics/{}'.format(sample_service.id, fake_uuid),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == 'No result found'
    assert json_resp['result'] == 'error'


def test_get_template_statistics_by_id_returns_empty_for_old_notification(
    notify_db,
    notify_db_session,
    client,
    sample_template
):
    sample_notification_history(notify_db, notify_db_session, sample_template)

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template-statistics/{}'.format(sample_template.service.id, sample_template.id),
        headers=[('Content-Type', 'application/json'), auth_header],
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))['data']
    assert not json_resp
