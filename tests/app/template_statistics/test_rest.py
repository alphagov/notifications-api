from datetime import datetime, timedelta
import uuid

import pytest
from freezegun import freeze_time

from tests.app.conftest import sample_notification


# get_template_statistics_for_service_by_day

@pytest.mark.parametrize('query_string', [
    {},
    {'limit_days': 0},
    {'limit_days': 8},
    {'limit_days': 3.5},
    {'limit_days': 'blurk'},
])
def get_template_statistics_for_service_by_day_with_bad_arg_returns_400(admin_request, query_string):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=uuid.uuid4(),
        **query_string,
        _expected_status=400
    )
    assert json_resp['result'] == 'error'
    assert 'limit_days' in json_resp['message']


def test_get_template_statistics_for_service_by_day_returns_template_info(admin_request, mocker, sample_notification):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_notification.service_id,
        limit_days=1
    )

    assert len(json_resp) == 1

    assert json_resp['data'][0]['count'] == 1
    assert json_resp['data'][0]['template_id'] == str(sample_notification.template_id)
    assert json_resp['data'][0]['template_name'] == 'Template Name'
    assert json_resp['data'][0]['template_type'] == 'sms'


def test_get_template_statistics_for_service_by_day_gets_out_of_redis_if_available(admin_request, mocker):
    assert False


def test_get_template_statistics_for_service_by_day_goes_to_db_if_not_in_redis(admin_request, mocker):
    assert False


def test_get_template_statistics_for_service_by_day_gets_stats_for_correct_days(admin_request, mocker):
    assert False


def test_get_template_statistics_for_service_by_day_returns_empty_list_if_no_templates(
    admin_request,
    mocker,
    sample_service
):
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_service.id,
        limit_days=1
    )

    assert len(json_resp['data']) == 0

# get_template_statistics_for_template


def test_get_template_statistics_for_template_returns_last_notification(
        notify_db,
        notify_db_session,
        admin_request):
    sample_notification(notify_db, notify_db_session)
    sample_notification(notify_db, notify_db_session)
    notification_3 = sample_notification(notify_db, notify_db_session)

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
