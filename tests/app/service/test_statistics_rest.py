import uuid
from datetime import datetime

import pytest
from freezegun import freeze_time

from app.celery.scheduled_tasks import daily_stats_template_usage_by_month
from app.models import EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, PRECOMPILED_TEMPLATE_NAME

from tests.app.db import (
    create_template,
    create_notification,
)


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_correct_data(
        admin_request,
        sample_template
):
    create_notification(sample_template, created_at=datetime(2016, 4, 1), status='created')
    create_notification(sample_template, created_at=datetime(2017, 4, 1), status='sending')
    create_notification(sample_template, created_at=datetime(2017, 4, 1), status='permanent-failure')
    create_notification(sample_template, created_at=datetime(2017, 4, 1), status='temporary-failure')

    daily_stats_template_usage_by_month()

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
def test_get_template_usage_by_month_returns_no_data(admin_request, sample_template):
    create_notification(sample_template, created_at=datetime(2016, 4, 1), status='created')

    daily_stats_template_usage_by_month()

    create_notification(sample_template, created_at=datetime.utcnow())

    resp_json = admin_request.get(
        'service.get_monthly_template_usage',
        service_id=sample_template.service_id,
        year=2015
    )
    assert resp_json['stats'] == []


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_two_templates(admin_request, sample_template, sample_service):
    template_one = create_template(
        sample_service,
        template_type=LETTER_TYPE,
        template_name=PRECOMPILED_TEMPLATE_NAME,
        hidden=True
    )

    create_notification(template_one, created_at=datetime(2017, 4, 1), status='created')
    create_notification(sample_template, created_at=datetime(2017, 4, 1), status='sending')
    create_notification(sample_template, created_at=datetime(2017, 4, 1), status='permanent-failure')
    create_notification(sample_template, created_at=datetime(2017, 4, 1), status='temporary-failure')

    daily_stats_template_usage_by_month()

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
def test_get_service_notification_statistics(admin_request, sample_template, today_only, stats):
    with freeze_time('2000-01-01T12:00:00'):
        create_notification(sample_template, status='delivered')
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
