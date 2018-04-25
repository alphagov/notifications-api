from decimal import Decimal

from datetime import datetime, timedelta
from freezegun import freeze_time

from app import db
from app.dao.fact_billing_dao import fetch_annual_billing_for_year, fetch_billing_data_for_day
from app.models import FactBilling
from app.utils import convert_utc_to_bst
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template,
    create_notification
)


def test_fetch_billing_data_for_today_includes_data_with_the_right_status(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for status in ['delivered', 'sending', 'temporary-failure', 'created', 'technical-failure']:
        create_notification(template=template, status=status)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 1
    assert results[0].notifications_sent == 3


def test_fetch_billing_data_for_today_includes_data_with_the_right_key_type(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for key_type in ['normal', 'test', 'team']:
        create_notification(template=template, status='delivered', key_type=key_type)

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_today_includes_data_with_the_right_date(notify_db_session):
    process_day = datetime(2018, 4, 1, 13, 30, 00)
    service = create_service()
    template = create_template(service=service, template_type="email")
    create_notification(template=template, status='delivered', created_at=process_day)
    create_notification(template=template, status='delivered', created_at=datetime(2018, 3, 31, 23, 23, 23))

    create_notification(template=template, status='delivered', created_at=datetime(2018, 3, 31, 20, 23, 23))
    create_notification(template=template, status='sending', created_at=process_day + timedelta(days=1))

    day_under_test = convert_utc_to_bst(process_day)
    results = fetch_billing_data_for_day(day_under_test)
    assert len(results) == 1
    assert results[0].notifications_sent == 2


def test_fetch_billing_data_for_day_is_grouped_by_template(notify_db_session):
    service = create_service()
    email_template = create_template(service=service, template_type="email")
    sms_template = create_template(service=service, template_type="email")
    create_notification(template=email_template, status='delivered')
    create_notification(template=sms_template, status='delivered')

    today = convert_utc_to_bst(datetime.utcnow())
    results = fetch_billing_data_for_day(today)
    assert len(results) == 2
    assert results[0].notifications_sent == 1
    assert results[1].notifications_sent == 1


def test_fetch_annual_billing_for_year(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="sms")
    for i in range(1, 31):
        create_ft_billing(bst_date='2018-06-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='sms',
                          rate=0.162)
    for i in range(1, 32):
        create_ft_billing(bst_date='2018-07-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='sms',
                          rate=0.158)

    results = fetch_annual_billing_for_year(service_id=service.id,
                                            year=2018)

    assert len(results) == 2
    assert results[0][0] == 6.0
    assert results[0][1] == 30
    assert results[0][2] == Decimal('30')
    assert results[0][3] == service.id
    assert results[0][4] == Decimal('0.162')
    assert results[0][5] == Decimal('1')
    assert results[0][6] is False

    assert results[1][0] == 7.0
    assert results[1][1] == 31
    assert results[1][2] == Decimal('31')
    assert results[1][3] == service.id
    assert results[1][4] == Decimal('0.158')
    assert results[1][5] == Decimal('1')
    assert results[1][6] is False


@freeze_time('2018-08-01 13:30:00')
def test_fetch_annual_billing_for_year_adds_data_for_today(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for i in range(1, 32):
        create_ft_billing(bst_date='2018-07-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='email',
                          rate=0.162)
    create_notification(template=template, status='delivered')

    assert db.session.query(FactBilling.bst_date).count() == 31
    results = fetch_annual_billing_for_year(service_id=service.id,
                                            year=2018)
    assert db.session.query(FactBilling.bst_date).count() == 32
    assert len(results) == 2
