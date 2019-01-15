import uuid
from datetime import datetime, date

import pytest
from freezegun import freeze_time

from app.models import (
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    PRECOMPILED_TEMPLATE_NAME,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    KEY_TYPE_NORMAL,
)

from tests.app.db import (
    create_service,
    create_template,
    create_notification,
    create_ft_notification_status
)


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_correct_data(
        admin_request,
        sample_template
):
    create_ft_notification_status(bst_date=date(2017, 4, 2), template=sample_template, count=3)
    create_notification(sample_template, created_at=datetime.utcnow())

    resp_json = admin_request.get(
        'service.get_monthly_template_usage',
        service_id=sample_template.service_id,
        year=2017
    )
    resp_json = resp_json['stats']

    assert len(resp_json) == 2

    assert resp_json[0]["template_id"] == str(sample_template.id)
    assert resp_json[0]["name"] == sample_template.name
    assert resp_json[0]["type"] == sample_template.template_type
    assert resp_json[0]["month"] == 4
    assert resp_json[0]["year"] == 2017
    assert resp_json[0]["count"] == 3

    assert resp_json[1]["template_id"] == str(sample_template.id)
    assert resp_json[1]["name"] == sample_template.name
    assert resp_json[1]["type"] == sample_template.template_type
    assert resp_json[1]["month"] == 11
    assert resp_json[1]["year"] == 2017
    assert resp_json[1]["count"] == 1


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_two_templates(admin_request, sample_template, sample_service):
    template_one = create_template(
        sample_service,
        template_type=LETTER_TYPE,
        template_name=PRECOMPILED_TEMPLATE_NAME,
        hidden=True
    )
    create_ft_notification_status(bst_date=datetime(2017, 4, 1), template=template_one, count=1)
    create_ft_notification_status(bst_date=datetime(2017, 4, 1), template=sample_template, count=3)
    create_notification(sample_template, created_at=datetime.utcnow())

    resp_json = admin_request.get(
        'service.get_monthly_template_usage',
        service_id=sample_template.service_id,
        year=2017
    )

    resp_json = sorted(resp_json['stats'], key=lambda k: (k['year'], k['month'], k['count']))
    assert len(resp_json) == 3

    assert resp_json[0]["template_id"] == str(template_one.id)
    assert resp_json[0]["name"] == template_one.name
    assert resp_json[0]["type"] == template_one.template_type
    assert resp_json[0]["month"] == 4
    assert resp_json[0]["year"] == 2017
    assert resp_json[0]["count"] == 1
    assert resp_json[0]["is_precompiled_letter"] is True

    assert resp_json[1]["template_id"] == str(sample_template.id)
    assert resp_json[1]["name"] == sample_template.name
    assert resp_json[1]["type"] == sample_template.template_type
    assert resp_json[1]["month"] == 4
    assert resp_json[1]["year"] == 2017
    assert resp_json[1]["count"] == 3
    assert resp_json[1]["is_precompiled_letter"] is False

    assert resp_json[2]["template_id"] == str(sample_template.id)
    assert resp_json[2]["name"] == sample_template.name
    assert resp_json[2]["type"] == sample_template.template_type
    assert resp_json[2]["month"] == 11
    assert resp_json[2]["year"] == 2017
    assert resp_json[2]["count"] == 1
    assert resp_json[2]["is_precompiled_letter"] is False


@pytest.mark.parametrize('today_only, stats', [
    (False, {'requested': 2, 'delivered': 1, 'failed': 0}),
    (True, {'requested': 1, 'delivered': 0, 'failed': 0})
], ids=['seven_days', 'today'])
def test_get_service_notification_statistics(admin_request, sample_service, sample_template, today_only, stats):
    create_ft_notification_status(date(2000, 1, 1), 'sms', sample_service, count=1)
    with freeze_time('2000-01-02T12:00:00'):
        create_notification(sample_template, status='created')
        resp = admin_request.get(
            'service.get_service_notification_statistics',
            service_id=sample_template.service_id,
            today_only=today_only
        )

    assert set(resp['data'].keys()) == {SMS_TYPE, EMAIL_TYPE, LETTER_TYPE}
    assert resp['data'][SMS_TYPE] == stats


def test_get_service_notification_statistics_with_unknown_service(admin_request):
    resp = admin_request.get(
        'service.get_service_notification_statistics',
        service_id=uuid.uuid4()
    )

    assert resp['data'] == {
        SMS_TYPE: {'requested': 0, 'delivered': 0, 'failed': 0},
        EMAIL_TYPE: {'requested': 0, 'delivered': 0, 'failed': 0},
        LETTER_TYPE: {'requested': 0, 'delivered': 0, 'failed': 0},
    }


@pytest.mark.parametrize('kwargs, expected_json', [
    ({'year': 'baz'}, {'message': 'Year must be a number', 'result': 'error'}),
    ({}, {'message': 'Year must be a number', 'result': 'error'}),
])
def test_get_monthly_notification_stats_returns_errors(admin_request, sample_service, kwargs, expected_json):
    response = admin_request.get(
        'service.get_monthly_notification_stats',
        service_id=sample_service.id,
        _expected_status=400,
        **kwargs
    )
    assert response == expected_json


def test_get_monthly_notification_stats_returns_404_if_no_service(admin_request):
    response = admin_request.get(
        'service.get_monthly_notification_stats',
        service_id=uuid.uuid4(),
        _expected_status=404,
    )
    assert response == {'message': 'No result found', 'result': 'error'}


def test_get_monthly_notification_stats_returns_empty_stats_with_correct_dates(admin_request, sample_service):
    response = admin_request.get(
        'service.get_monthly_notification_stats',
        service_id=sample_service.id,
        year=2016
    )
    assert len(response['data']) == 12

    keys = [
        '2016-04', '2016-05', '2016-06', '2016-07', '2016-08', '2016-09', '2016-10', '2016-11', '2016-12',
        '2017-01', '2017-02', '2017-03'
    ]
    assert sorted(response['data'].keys()) == keys
    for val in response['data'].values():
        assert val == {'sms': {}, 'email': {}, 'letter': {}}


def test_get_monthly_notification_stats_returns_stats(admin_request, sample_service):
    sms_t1 = create_template(sample_service)
    sms_t2 = create_template(sample_service)
    email_template = create_template(sample_service, template_type=EMAIL_TYPE)

    create_ft_notification_status(datetime(2016, 6, 1), template=sms_t1)
    create_ft_notification_status(datetime(2016, 6, 2), template=sms_t1)

    create_ft_notification_status(datetime(2016, 7, 1), template=sms_t1)
    create_ft_notification_status(datetime(2016, 7, 1), template=sms_t2)
    create_ft_notification_status(datetime(2016, 7, 1), template=sms_t1, notification_status='created')
    create_ft_notification_status(datetime(2016, 7, 1), template=email_template)

    response = admin_request.get(
        'service.get_monthly_notification_stats',
        service_id=sample_service.id,
        year=2016
    )
    assert len(response['data']) == 12

    assert response['data']['2016-06'] == {
        'sms': {
            # it combines the two days
            'delivered': 2
        },
        'email': {},
        'letter': {}
    }
    assert response['data']['2016-07'] == {
        # it combines the two template types
        'sms': {
            'created': 1,
            'delivered': 2,
        },
        'email': {
            'delivered': 1
        },
        'letter': {}
    }


@freeze_time('2016-06-05 12:00:00')
def test_get_monthly_notification_stats_combines_todays_data_and_historic_stats(admin_request, sample_template):
    create_ft_notification_status(datetime(2016, 5, 1), template=sample_template, count=1)
    create_ft_notification_status(datetime(2016, 6, 1), template=sample_template, notification_status='created', count=2)  # noqa

    create_notification(sample_template, created_at=datetime(2016, 6, 5), status='created')
    create_notification(sample_template, created_at=datetime(2016, 6, 5), status='delivered')

    # this doesn't get returned in the stats because it is old - it should be in ft_notification_status by now
    create_notification(sample_template, created_at=datetime(2016, 6, 4), status='sending')

    response = admin_request.get(
        'service.get_monthly_notification_stats',
        service_id=sample_template.service_id,
        year=2016
    )

    assert len(response['data']) == 3  # apr, may, jun
    assert response['data']['2016-05'] == {
        'sms': {
            'delivered': 1
        },
        'email': {},
        'letter': {}
    }
    assert response['data']['2016-06'] == {
        'sms': {
            # combines the stats from the historic ft_notification_status and the current notifications
            'created': 3,
            'delivered': 1,
        },
        'email': {},
        'letter': {}
    }


def test_get_monthly_notification_stats_ignores_test_keys(admin_request, sample_service):
    create_ft_notification_status(datetime(2016, 6, 1), service=sample_service, key_type=KEY_TYPE_NORMAL, count=1)
    create_ft_notification_status(datetime(2016, 6, 1), service=sample_service, key_type=KEY_TYPE_TEAM, count=2)
    create_ft_notification_status(datetime(2016, 6, 1), service=sample_service, key_type=KEY_TYPE_TEST, count=4)

    response = admin_request.get('service.get_monthly_notification_stats', service_id=sample_service.id, year=2016)

    assert response['data']['2016-06']['sms'] == {'delivered': 3}


def test_get_monthly_notification_stats_checks_dates(admin_request, sample_service):
    t = create_template(sample_service)
    create_ft_notification_status(datetime(2016, 3, 31), template=t, notification_status='created')
    create_ft_notification_status(datetime(2016, 4, 1), template=t, notification_status='sending')
    create_ft_notification_status(datetime(2017, 3, 31), template=t, notification_status='delivered')
    create_ft_notification_status(datetime(2017, 4, 11), template=t, notification_status='permanent-failure')

    response = admin_request.get('service.get_monthly_notification_stats', service_id=sample_service.id, year=2016)

    assert '2016-03' not in response['data']
    assert '2017-04' not in response['data']
    assert response['data']['2016-04']['sms'] == {'sending': 1}
    assert response['data']['2017-03']['sms'] == {'delivered': 1}


def test_get_monthly_notification_stats_only_gets_for_one_service(admin_request, notify_db_session):
    services = [create_service(), create_service(service_name="2")]

    templates = [create_template(services[0]), create_template(services[1])]

    create_ft_notification_status(datetime(2016, 6, 1), template=templates[0], notification_status='created')
    create_ft_notification_status(datetime(2016, 6, 1), template=templates[1], notification_status='delivered')

    response = admin_request.get('service.get_monthly_notification_stats', service_id=services[0].id, year=2016)

    assert response['data']['2016-06'] == {
        'sms': {'created': 1},
        'email': {},
        'letter': {}
    }
