from datetime import timedelta, datetime, date
from uuid import UUID

import pytest
import mock

from app.dao.fact_notification_status_dao import (
    update_fact_notification_status,
    fetch_notification_status_for_day,
    fetch_notification_status_for_service_by_month,
    fetch_notification_status_for_service_for_day,
    fetch_notification_status_for_service_for_today_and_7_previous_days,
    fetch_notification_status_totals_for_all_services,
    fetch_notification_statuses_for_job,
    fetch_stats_for_all_services_by_date_range, fetch_monthly_template_usage_for_service
)
from app.models import FactNotificationStatus, KEY_TYPE_TEST, KEY_TYPE_TEAM, EMAIL_TYPE, SMS_TYPE, LETTER_TYPE
from freezegun import freeze_time
from tests.app.db import create_notification, create_service, create_template, create_ft_notification_status, create_job


def test_update_fact_notification_status(notify_db_session):
    first_service = create_service(service_name='First Service')
    first_template = create_template(service=first_service)
    second_service = create_service(service_name='second Service')
    second_template = create_template(service=second_service, template_type='email')
    third_service = create_service(service_name='third Service')
    third_template = create_template(service=third_service, template_type='letter')

    create_notification(template=first_template, status='delivered')
    create_notification(template=first_template, created_at=datetime.utcnow() - timedelta(days=1))
    create_notification(template=second_template, status='temporary-failure')
    create_notification(template=second_template, created_at=datetime.utcnow() - timedelta(days=1))
    create_notification(template=third_template, status='created')
    create_notification(template=third_template, created_at=datetime.utcnow() - timedelta(days=1))

    process_day = datetime.utcnow()
    data = fetch_notification_status_for_day(process_day=process_day)
    update_fact_notification_status(data=data, process_day=process_day)

    new_fact_data = FactNotificationStatus.query.order_by(FactNotificationStatus.bst_date,
                                                          FactNotificationStatus.notification_type
                                                          ).all()

    assert len(new_fact_data) == 3
    assert new_fact_data[0].bst_date == process_day.date()
    assert new_fact_data[0].template_id == second_template.id
    assert new_fact_data[0].service_id == second_service.id
    assert new_fact_data[0].job_id == UUID('00000000-0000-0000-0000-000000000000')
    assert new_fact_data[0].notification_type == 'email'
    assert new_fact_data[0].notification_status == 'temporary-failure'
    assert new_fact_data[0].notification_count == 1

    assert new_fact_data[1].bst_date == process_day.date()
    assert new_fact_data[1].template_id == third_template.id
    assert new_fact_data[1].service_id == third_service.id
    assert new_fact_data[1].job_id == UUID('00000000-0000-0000-0000-000000000000')
    assert new_fact_data[1].notification_type == 'letter'
    assert new_fact_data[1].notification_status == 'created'
    assert new_fact_data[1].notification_count == 1

    assert new_fact_data[2].bst_date == process_day.date()
    assert new_fact_data[2].template_id == first_template.id
    assert new_fact_data[2].service_id == first_service.id
    assert new_fact_data[2].job_id == UUID('00000000-0000-0000-0000-000000000000')
    assert new_fact_data[2].notification_type == 'sms'
    assert new_fact_data[2].notification_status == 'delivered'
    assert new_fact_data[2].notification_count == 1


def test__update_fact_notification_status_updates_row(notify_db_session):
    first_service = create_service(service_name='First Service')
    first_template = create_template(service=first_service)
    create_notification(template=first_template, status='delivered')

    process_day = datetime.utcnow()
    data = fetch_notification_status_for_day(process_day=process_day)
    update_fact_notification_status(data=data, process_day=process_day)

    new_fact_data = FactNotificationStatus.query.order_by(FactNotificationStatus.bst_date,
                                                          FactNotificationStatus.notification_type
                                                          ).all()
    assert len(new_fact_data) == 1
    assert new_fact_data[0].notification_count == 1

    create_notification(template=first_template, status='delivered')

    data = fetch_notification_status_for_day(process_day=process_day)
    update_fact_notification_status(data=data, process_day=process_day)

    updated_fact_data = FactNotificationStatus.query.order_by(FactNotificationStatus.bst_date,
                                                              FactNotificationStatus.notification_type
                                                              ).all()
    assert len(updated_fact_data) == 1
    assert updated_fact_data[0].notification_count == 2


def test_fetch_notification_status_for_service_by_month(notify_db_session):
    service_1 = create_service(service_name='service_1')
    service_2 = create_service(service_name='service_2')

    create_ft_notification_status(date(2018, 1, 1), 'sms', service_1, count=4)
    create_ft_notification_status(date(2018, 1, 2), 'sms', service_1, count=10)
    create_ft_notification_status(date(2018, 1, 2), 'sms', service_1, notification_status='created')
    create_ft_notification_status(date(2018, 1, 3), 'email', service_1)

    create_ft_notification_status(date(2018, 2, 2), 'sms', service_1)

    # not included - too early
    create_ft_notification_status(date(2017, 12, 31), 'sms', service_1)
    # not included - too late
    create_ft_notification_status(date(2017, 3, 1), 'sms', service_1)
    # not included - wrong service
    create_ft_notification_status(date(2018, 1, 3), 'sms', service_2)
    # not included - test keys
    create_ft_notification_status(date(2018, 1, 3), 'sms', service_1, key_type=KEY_TYPE_TEST)

    results = sorted(
        fetch_notification_status_for_service_by_month(date(2018, 1, 1), date(2018, 2, 28), service_1.id),
        key=lambda x: (x.month, x.notification_type, x.notification_status)
    )

    assert len(results) == 4

    assert results[0].month.date() == date(2018, 1, 1)
    assert results[0].notification_type == 'email'
    assert results[0].notification_status == 'delivered'
    assert results[0].count == 1

    assert results[1].month.date() == date(2018, 1, 1)
    assert results[1].notification_type == 'sms'
    assert results[1].notification_status == 'created'
    assert results[1].count == 1

    assert results[2].month.date() == date(2018, 1, 1)
    assert results[2].notification_type == 'sms'
    assert results[2].notification_status == 'delivered'
    assert results[2].count == 14

    assert results[3].month.date() == date(2018, 2, 1)
    assert results[3].notification_type == 'sms'
    assert results[3].notification_status == 'delivered'
    assert results[3].count == 1


def test_fetch_notification_status_for_service_for_day(notify_db_session):
    service_1 = create_service(service_name='service_1')
    service_2 = create_service(service_name='service_2')

    create_template(service=service_1)
    create_template(service=service_2)

    # too early
    create_notification(service_1.templates[0], created_at=datetime(2018, 5, 31, 22, 59, 0))

    # included
    create_notification(service_1.templates[0], created_at=datetime(2018, 5, 31, 23, 0, 0))
    create_notification(service_1.templates[0], created_at=datetime(2018, 6, 1, 22, 59, 0))
    create_notification(service_1.templates[0], created_at=datetime(2018, 6, 1, 12, 0, 0), key_type=KEY_TYPE_TEAM)
    create_notification(service_1.templates[0], created_at=datetime(2018, 6, 1, 12, 0, 0), status='delivered')

    # test key
    create_notification(service_1.templates[0], created_at=datetime(2018, 6, 1, 12, 0, 0), key_type=KEY_TYPE_TEST)

    # wrong service
    create_notification(service_2.templates[0], created_at=datetime(2018, 6, 1, 12, 0, 0))

    # tomorrow (somehow)
    create_notification(service_1.templates[0], created_at=datetime(2018, 6, 1, 23, 0, 0))

    results = sorted(
        fetch_notification_status_for_service_for_day(datetime(2018, 6, 1), service_1.id),
        key=lambda x: x.notification_status
    )
    assert len(results) == 2

    assert results[0].month == datetime(2018, 6, 1, 0, 0)
    assert results[0].notification_type == 'sms'
    assert results[0].notification_status == 'created'
    assert results[0].count == 3

    assert results[1].month == datetime(2018, 6, 1, 0, 0)
    assert results[1].notification_type == 'sms'
    assert results[1].notification_status == 'delivered'
    assert results[1].count == 1


@freeze_time('2018-10-31T18:00:00')
def test_fetch_notification_status_for_service_for_today_and_7_previous_days(notify_db_session):
    service_1 = create_service(service_name='service_1')
    sms_template = create_template(service=service_1, template_type=SMS_TYPE)
    sms_template_2 = create_template(service=service_1, template_type=SMS_TYPE)
    email_template = create_template(service=service_1, template_type=EMAIL_TYPE)

    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, count=10)
    create_ft_notification_status(date(2018, 10, 24), 'sms', service_1, count=8)
    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, notification_status='created')
    create_ft_notification_status(date(2018, 10, 29), 'email', service_1, count=3)
    create_ft_notification_status(date(2018, 10, 26), 'letter', service_1, count=5)

    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(sms_template_2, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(sms_template, created_at=datetime(2018, 10, 31, 12, 0, 0), status='delivered')
    create_notification(email_template, created_at=datetime(2018, 10, 31, 13, 0, 0), status='delivered')

    # too early, shouldn't be included
    create_notification(service_1.templates[0], created_at=datetime(2018, 10, 30, 12, 0, 0), status='delivered')

    results = sorted(
        fetch_notification_status_for_service_for_today_and_7_previous_days(service_1.id),
        key=lambda x: (x.notification_type, x.status)
    )

    assert len(results) == 4

    assert results[0].notification_type == 'email'
    assert results[0].status == 'delivered'
    assert results[0].count == 4

    assert results[1].notification_type == 'letter'
    assert results[1].status == 'delivered'
    assert results[1].count == 5

    assert results[2].notification_type == 'sms'
    assert results[2].status == 'created'
    assert results[2].count == 3

    assert results[3].notification_type == 'sms'
    assert results[3].status == 'delivered'
    assert results[3].count == 19


@freeze_time('2018-10-31T18:00:00')
def test_fetch_notification_status_by_template_for_service_for_today_and_7_previous_days(notify_db_session):
    service_1 = create_service(service_name='service_1')
    sms_template = create_template(template_name='sms Template 1', service=service_1, template_type=SMS_TYPE)
    sms_template_2 = create_template(template_name='sms Template 2', service=service_1, template_type=SMS_TYPE)
    email_template = create_template(service=service_1, template_type=EMAIL_TYPE)

    # create unused email template
    create_template(service=service_1, template_type=EMAIL_TYPE)

    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, count=10)
    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, count=11)
    create_ft_notification_status(date(2018, 10, 24), 'sms', service_1, count=8)
    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, notification_status='created')
    create_ft_notification_status(date(2018, 10, 29), 'email', service_1, count=3)
    create_ft_notification_status(date(2018, 10, 26), 'letter', service_1, count=5)

    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(sms_template, created_at=datetime(2018, 10, 31, 12, 0, 0), status='delivered')
    create_notification(sms_template_2, created_at=datetime(2018, 10, 31, 12, 0, 0), status='delivered')
    create_notification(email_template, created_at=datetime(2018, 10, 31, 13, 0, 0), status='delivered')

    # too early, shouldn't be included
    create_notification(service_1.templates[0], created_at=datetime(2018, 10, 30, 12, 0, 0), status='delivered')

    results = fetch_notification_status_for_service_for_today_and_7_previous_days(service_1.id, by_template=True)

    assert [
        ('email Template Name', False, mock.ANY, 'email', 'delivered', 1),
        ('email Template Name', False, mock.ANY, 'email', 'delivered', 3),
        ('letter Template Name', False, mock.ANY, 'letter', 'delivered', 5),
        ('sms Template 1', False, mock.ANY, 'sms', 'created', 1),
        ('sms Template Name', False, mock.ANY, 'sms', 'created', 1),
        ('sms Template 1', False, mock.ANY, 'sms', 'delivered', 1),
        ('sms Template 2', False, mock.ANY, 'sms', 'delivered', 1),
        ('sms Template Name', False, mock.ANY, 'sms', 'delivered', 8),
        ('sms Template Name', False, mock.ANY, 'sms', 'delivered', 10),
        ('sms Template Name', False, mock.ANY, 'sms', 'delivered', 11),
    ] == sorted(results, key=lambda x: (x.notification_type, x.status, x.template_name, x.count))


@pytest.mark.parametrize(
    "start_date, end_date, expected_email, expected_letters, expected_sms, expected_created_sms",
    [
        (29, 30, 3, 10, 10, 1),  # not including today
        (29, 31, 4, 10, 11, 2),  # today included
        (26, 31, 4, 15, 11, 2),
    ]

)
@freeze_time('2018-10-31 14:00')
def test_fetch_notification_status_totals_for_all_services(
        notify_db_session,
        start_date,
        end_date,
        expected_email,
        expected_letters,
        expected_sms,
        expected_created_sms
):
    set_up_data()

    results = sorted(
        fetch_notification_status_totals_for_all_services(
            start_date=date(2018, 10, start_date), end_date=date(2018, 10, end_date)),
        key=lambda x: (x.notification_type, x.status)
    )

    assert len(results) == 4

    assert results[0].notification_type == 'email'
    assert results[0].status == 'delivered'
    assert results[0].count == expected_email

    assert results[1].notification_type == 'letter'
    assert results[1].status == 'delivered'
    assert results[1].count == expected_letters

    assert results[2].notification_type == 'sms'
    assert results[2].status == 'created'
    assert results[2].count == expected_created_sms

    assert results[3].notification_type == 'sms'
    assert results[3].status == 'delivered'
    assert results[3].count == expected_sms


def set_up_data():
    service_2 = create_service(service_name='service_2')
    create_template(service=service_2, template_type=LETTER_TYPE)
    service_1 = create_service(service_name='service_1')
    sms_template = create_template(service=service_1, template_type=SMS_TYPE)
    email_template = create_template(service=service_1, template_type=EMAIL_TYPE)
    create_ft_notification_status(date(2018, 10, 24), 'sms', service_1, count=8)
    create_ft_notification_status(date(2018, 10, 26), 'letter', service_1, count=5)
    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, count=10)
    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, notification_status='created')
    create_ft_notification_status(date(2018, 10, 29), 'email', service_1, count=3)
    create_ft_notification_status(date(2018, 10, 29), 'letter', service_2, count=10)

    create_notification(service_1.templates[0], created_at=datetime(2018, 10, 30, 12, 0, 0), status='delivered')
    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0))
    create_notification(sms_template, created_at=datetime(2018, 10, 31, 12, 0, 0), status='delivered')
    create_notification(email_template, created_at=datetime(2018, 10, 31, 13, 0, 0), status='delivered')
    return service_1, service_2


def test_fetch_notification_statuses_for_job(sample_template):
    j1 = create_job(sample_template)
    j2 = create_job(sample_template)

    create_ft_notification_status(date(2018, 10, 1), job=j1, notification_status='created', count=1)
    create_ft_notification_status(date(2018, 10, 1), job=j1, notification_status='delivered', count=2)
    create_ft_notification_status(date(2018, 10, 2), job=j1, notification_status='created', count=4)
    create_ft_notification_status(date(2018, 10, 1), job=j2, notification_status='created', count=8)

    assert {x.status: x.count for x in fetch_notification_statuses_for_job(j1.id)} == {
        'created': 5,
        'delivered': 2
    }


@freeze_time('2018-10-31 14:00')
def test_fetch_stats_for_all_services_by_date_range(notify_db_session):
    service_1, service_2 = set_up_data()
    results = fetch_stats_for_all_services_by_date_range(start_date=date(2018, 10, 29),
                                                         end_date=date(2018, 10, 31))
    assert len(results) == 5

    assert results[0].service_id == service_1.id
    assert results[0].notification_type == 'email'
    assert results[0].status == 'delivered'
    assert results[0].count == 4

    assert results[1].service_id == service_1.id
    assert results[1].notification_type == 'sms'
    assert results[1].status == 'created'
    assert results[1].count == 2

    assert results[2].service_id == service_1.id
    assert results[2].notification_type == 'sms'
    assert results[2].status == 'delivered'
    assert results[2].count == 11

    assert results[3].service_id == service_2.id
    assert results[3].notification_type == 'letter'
    assert results[3].status == 'delivered'
    assert results[3].count == 10

    assert results[4].service_id == service_2.id
    assert not results[4].notification_type
    assert not results[4].status
    assert not results[4].count


@freeze_time('2018-03-30 14:00')
def test_fetch_monthly_template_usage_for_service(sample_service):
    template_one = create_template(service=sample_service, template_type='sms', template_name='a')
    template_two = create_template(service=sample_service, template_type='email', template_name='b')
    template_three = create_template(service=sample_service, template_type='letter', template_name='c')

    create_ft_notification_status(bst_date=date(2017, 12, 10),
                                  service=sample_service,
                                  template=template_two,
                                  count=3)
    create_ft_notification_status(bst_date=date(2017, 12, 10),
                                  service=sample_service,
                                  template=template_one,
                                  count=6)

    create_ft_notification_status(bst_date=date(2018, 1, 1),
                                  service=sample_service,
                                  template=template_one,
                                  count=4)

    create_ft_notification_status(bst_date=date(2018, 3, 1),
                                  service=sample_service,
                                  template=template_three,
                                  count=5)
    create_notification(template=template_three, created_at=datetime.utcnow() - timedelta(days=1))
    create_notification(template=template_three, created_at=datetime.utcnow())
    results = fetch_monthly_template_usage_for_service(
        datetime(2017, 4, 1), datetime(2018, 3, 31), sample_service.id
    )

    assert len(results) == 4

    assert results[0].template_id == template_one.id
    assert results[0].name == template_one.name
    assert results[0].is_precompiled_letter is False
    assert results[0].template_type == template_one.template_type
    assert results[0].month == 12
    assert results[0].year == 2017
    assert results[0].count == 6
    assert results[1].template_id == template_two.id
    assert results[1].name == template_two.name
    assert results[1].is_precompiled_letter is False
    assert results[1].template_type == template_two.template_type
    assert results[1].month == 12
    assert results[1].year == 2017
    assert results[1].count == 3

    assert results[2].template_id == template_one.id
    assert results[2].name == template_one.name
    assert results[2].is_precompiled_letter is False
    assert results[2].template_type == template_one.template_type
    assert results[2].month == 1
    assert results[2].year == 2018
    assert results[2].count == 4

    assert results[3].template_id == template_three.id
    assert results[3].name == template_three.name
    assert results[3].is_precompiled_letter is False
    assert results[3].template_type == template_three.template_type
    assert results[3].month == 3
    assert results[3].year == 2018
    assert results[3].count == 6


@freeze_time('2018-03-30 14:00')
def test_fetch_monthly_template_usage_for_service_does_join_to_notifications_if_today_is_not_in_date_range(
        sample_service
):
    template_one = create_template(service=sample_service, template_type='sms', template_name='a')
    template_two = create_template(service=sample_service, template_type='email', template_name='b')
    create_ft_notification_status(bst_date=date(2018, 2, 1),
                                  service=template_two.service,
                                  template=template_two,
                                  count=15)
    create_ft_notification_status(bst_date=date(2018, 2, 2),
                                  service=template_one.service,
                                  template=template_one,
                                  count=20)
    create_ft_notification_status(bst_date=date(2018, 3, 1),
                                  service=template_one.service,
                                  template=template_one,
                                  count=3)
    create_notification(template=template_one, created_at=datetime.utcnow())
    results = fetch_monthly_template_usage_for_service(
        datetime(2018, 1, 1), datetime(2018, 2, 20), template_one.service_id
    )

    assert len(results) == 2

    assert results[0].template_id == template_one.id
    assert results[0].name == template_one.name
    assert results[0].is_precompiled_letter == template_one.is_precompiled_letter
    assert results[0].template_type == template_one.template_type
    assert results[0].month == 2
    assert results[0].year == 2018
    assert results[0].count == 20
    assert results[1].template_id == template_two.id
    assert results[1].name == template_two.name
    assert results[1].is_precompiled_letter == template_two.is_precompiled_letter
    assert results[1].template_type == template_two.template_type
    assert results[1].month == 2
    assert results[1].year == 2018
    assert results[1].count == 15


@freeze_time('2018-03-30 14:00')
def test_fetch_monthly_template_usage_for_service_does_not_include_cancelled_status(
        sample_template
):
    create_ft_notification_status(bst_date=date(2018, 3, 1),
                                  service=sample_template.service,
                                  template=sample_template,
                                  notification_status='cancelled',
                                  count=15)
    create_notification(template=sample_template, created_at=datetime.utcnow(), status='cancelled')
    results = fetch_monthly_template_usage_for_service(
        datetime(2018, 1, 1), datetime(2018, 3, 31), sample_template.service_id
    )

    assert len(results) == 0
