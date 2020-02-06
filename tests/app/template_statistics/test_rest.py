import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from freezegun import freeze_time

from app import DATETIME_FORMAT
from tests.app.db import create_ft_notification_status, create_notification


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
    assert json_resp['data'][0]['template_name'] == 'sms Template Name'
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


@freeze_time('2018-01-02 12:00:00')
def test_get_template_statistics_for_service_by_day_goes_to_db(
    admin_request,
    mocker,
    sample_template
):

    # first time it is called redis returns data, second time returns none
    mock_dao = mocker.patch(
        'app.template_statistics.rest.fetch_notification_status_for_service_for_today_and_7_previous_days',
        return_value=[
            Mock(
                template_id=sample_template.id,
                count=3,
                template_name=sample_template.name,
                notification_type=sample_template.template_type,
                status='created',
                is_precompiled_letter=False
            )
        ]
    )
    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_template.service_id,
        whole_days=1
    )

    assert json_resp['data'] == [{
        "template_id": str(sample_template.id),
        "count": 3,
        "template_name": sample_template.name,
        "template_type": sample_template.template_type,
        "status": "created",
        "is_precompiled_letter": False

    }]
    # dao only called for 2nd, since redis returned values for first call
    mock_dao.assert_called_once_with(
        str(sample_template.service_id), limit_days=1, by_template=True
    )


def test_get_template_statistics_for_service_by_day_returns_empty_list_if_no_templates(
    admin_request,
    mocker,
    sample_service
):

    json_resp = admin_request.get(
        'template_statistics.get_template_statistics_for_service_by_day',
        service_id=sample_service.id,
        whole_days=7
    )

    assert len(json_resp['data']) == 0


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


def test_get_last_used_datetime_for_template(
    admin_request, sample_template
):
    date_from_notification = datetime.utcnow() - timedelta(hours=2)
    create_notification(template=sample_template, created_at=date_from_notification)
    date_from_ft_status = (datetime.utcnow() - timedelta(days=2)).date()
    create_ft_notification_status(bst_date=date_from_ft_status,
                                  template=sample_template)

    json_resp = admin_request.get(
        'template_statistics.get_last_used_datetime_for_template',
        service_id=str(sample_template.service_id),
        template_id=sample_template.id
    )
    assert json_resp['last_date_used'] == date_from_notification.strftime(DATETIME_FORMAT)


def test_get_last_used_datetime_for_template_returns_none_if_no_usage_of_template(
    admin_request, sample_template
):
    json_resp = admin_request.get(
        'template_statistics.get_last_used_datetime_for_template',
        service_id=str(sample_template.service_id),
        template_id=sample_template.id
    )
    assert json_resp['last_date_used'] is None


def test_get_last_used_datetime_for_template_returns_400_if_service_does_not_exist(
    admin_request, sample_template
):
    admin_request.get(
        'template_statistics.get_last_used_datetime_for_template',
        service_id=uuid.uuid4(),
        template_id=sample_template.id,
        _expected_status=404
    )


def test_get_last_used_datetime_for_template_returns_404_if_template_does_not_exist(
    admin_request, sample_template
):
    admin_request.get(
        'template_statistics.get_last_used_datetime_for_template',
        service_id=sample_template.service_id,
        template_id=uuid.uuid4(),
        _expected_status=404
    )
