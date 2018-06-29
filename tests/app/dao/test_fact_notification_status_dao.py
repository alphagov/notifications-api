from datetime import timedelta, datetime, date
from uuid import UUID

from app.dao.fact_notification_status_dao import (
    update_fact_notification_status,
    fetch_notification_status_for_day,
    fetch_notification_status_for_service_by_month,
    fetch_notification_status_for_service_for_day,
)
from app.models import FactNotificationStatus
from tests.app.db import create_notification, create_service, create_template, create_ft_notification_status


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
    create_notification(service_1.templates[0], created_at=datetime(2018, 6, 1, 22, 59, 0), status='delivered')

    # wrong service
    create_notification(service_2.templates[0], created_at=datetime(2018, 5, 31, 23, 0, 0))

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
    assert results[0].count == 2

    assert results[1].month == datetime(2018, 6, 1, 0, 0)
    assert results[1].notification_type == 'sms'
    assert results[1].notification_status == 'delivered'
    assert results[1].count == 1
