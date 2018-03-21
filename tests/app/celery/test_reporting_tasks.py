from datetime import datetime, timedelta, date
from tests.app.conftest import sample_notification
from app.celery.reporting_tasks import create_nightly_billing, get_rate
from app.models import (FactBilling,
                        Notification,
                        LETTER_TYPE,
                        EMAIL_TYPE,
                        SMS_TYPE)
from decimal import Decimal
import pytest
from app.dao.letter_rate_dao import dao_create_letter_rate
from app.models import LetterRate, Rate
from app import db
from freezegun import freeze_time
from sqlalchemy import desc


def test_reporting_should_have_decorated_tasks_functions():
    assert create_nightly_billing.__wrapped__.__name__ == 'create_nightly_billing'


def mocker_get_rate(non_letter_rates, letter_rates, notification_type, date, crown=None, rate_multiplier=None):
    if notification_type == LETTER_TYPE:
        return Decimal(2.1)
    elif notification_type == SMS_TYPE:
        return Decimal(1.33)
    elif notification_type == EMAIL_TYPE:
        return Decimal(0)


@pytest.mark.parametrize('second_rate, records_num, billable_units, multiplier',
                         [(1.0, 1, 2, [1]),
                          (2.0, 2, 1, [1, 2])])
def test_create_nightly_billing_sms_rate_multiplier(
        notify_db,
        notify_db_session,
        sample_service,
        sample_template,
        mocker,
        second_rate,
        records_num,
        billable_units,
        multiplier):

    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.celery.reporting_tasks.get_rate', side_effect=mocker_get_rate)

    # These are sms notifications
    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=second_rate,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing(yesterday)
    records = FactBilling.query.all()
    assert len(records) == records_num
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == billable_units
        assert record.rate_multiplier == multiplier[i]


def test_create_nightly_billing_different_templates(
        notify_db,
        notify_db_session,
        sample_service,
        sample_template,
        sample_email_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.celery.reporting_tasks.get_rate', side_effect=mocker_get_rate)

    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_email_template,
        status='delivered',
        sent_by='ses',
        international=False,
        rate_multiplier=0,
        billable_units=0,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing(yesterday)
    records = FactBilling.query.order_by('rate_multiplier').all()

    assert len(records) == 2
    multiplier = [0, 1]
    billable_units = [0, 1]
    rate = [0, Decimal(1.33)]
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == rate[i]
        assert record.billable_units == billable_units[i]
        assert record.rate_multiplier == multiplier[i]


def test_create_nightly_billing_different_sent_by(
        notify_db,
        notify_db_session,
        sample_service,
        sample_template,
        sample_email_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.celery.reporting_tasks.get_rate', side_effect=mocker_get_rate)

    # These are sms notifications
    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_template,
        status='delivered',
        sent_by='firetext',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing(yesterday)
    records = FactBilling.query.order_by('rate_multiplier').all()

    assert len(records) == 2
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == 1
        assert record.rate_multiplier == 1.0


def test_create_nightly_billing_letter(
        notify_db,
        notify_db_session,
        sample_service,
        sample_letter_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.celery.reporting_tasks.get_rate', side_effect=mocker_get_rate)

    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_letter_template,
        status='delivered',
        sent_by='dvla',
        international=False,
        rate_multiplier=2.0,
        billable_units=2,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing(yesterday)
    records = FactBilling.query.order_by('rate_multiplier').all()
    assert len(records) == 1
    record = records[0]
    assert record.notification_type == LETTER_TYPE
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(2.1)
    assert record.billable_units == 2
    assert record.rate_multiplier == 2.0


def test_create_nightly_billing_null_sent_by_sms(
        notify_db,
        notify_db_session,
        sample_service,
        sample_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.celery.reporting_tasks.get_rate', side_effect=mocker_get_rate)

    sample_notification(
        notify_db,
        notify_db_session,
        created_at=yesterday,
        service=sample_service,
        template=sample_template,
        status='delivered',
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing(yesterday)
    records = FactBilling.query.all()

    assert len(records) == 1
    record = records[0]
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(1.33)
    assert record.billable_units == 1
    assert record.rate_multiplier == 1
    assert record.provider == 'unknown'


@freeze_time('2018-01-15T03:30:00')
def test_create_nightly_billing_consolidate_from_3_days_delta(
        notify_db,
        notify_db_session,
        sample_service,
        sample_template,
        mocker):

    mocker.patch('app.celery.reporting_tasks.get_rate', side_effect=mocker_get_rate)

    # create records from 11th to 15th
    for i in range(0, 5):
        sample_notification(
            notify_db,
            notify_db_session,
            created_at=datetime.now() - timedelta(days=i),
            service=sample_service,
            template=sample_template,
            status='delivered',
            sent_by=None,
            international=False,
            rate_multiplier=1.0,
            billable_units=1,
        )

    notification = Notification.query.order_by(Notification.created_at).all()
    assert datetime.date(notification[0].created_at) == date(2018, 1, 11)

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing()
    records = FactBilling.query.order_by(FactBilling.bst_date).all()

    assert len(records) == 4
    assert records[0].bst_date == date(2018, 1, 12)
    assert records[-1].bst_date == date(2018, 1, 15)


def test_get_rate_for_letter_latest(notify_db, notify_db_session):
    letter_rate = LetterRate(start_date=datetime(2017, 12, 1),
                             rate=Decimal(0.33),
                             crown=True,
                             sheet_count=1,
                             post_class='second')

    dao_create_letter_rate(letter_rate)
    letter_rate = LetterRate(start_date=datetime(2016, 12, 1),
                             end_date=datetime(2017, 12, 1),
                             rate=Decimal(0.30),
                             crown=True,
                             sheet_count=1,
                             post_class='second')
    dao_create_letter_rate(letter_rate)

    non_letter_rates = [(r.notification_type, r.valid_from, r.rate) for r in
                        Rate.query.order_by(desc(Rate.valid_from)).all()]
    letter_rates = [(r.start_date, r.crown, r.sheet_count, r.rate) for r in
                    LetterRate.query.order_by(desc(LetterRate.start_date)).all()]

    rate = get_rate(non_letter_rates, letter_rates, LETTER_TYPE, datetime(2018, 1, 1), True, 1)
    assert rate == Decimal(0.33)


def test_get_rate_for_sms_and_email(notify_db, notify_db_session):
    letter_rate = LetterRate(start_date=datetime(2017, 12, 1),
                             rate=Decimal(0.33),
                             crown=True,
                             sheet_count=1,
                             post_class='second')
    dao_create_letter_rate(letter_rate)
    sms_rate = Rate(valid_from=datetime(2017, 12, 1),
                    rate=Decimal(0.15),
                    notification_type=SMS_TYPE)
    db.session.add(sms_rate)
    email_rate = Rate(valid_from=datetime(2017, 12, 1),
                      rate=Decimal(0),
                      notification_type=EMAIL_TYPE)
    db.session.add(email_rate)

    non_letter_rates = [(r.notification_type, r.valid_from, r.rate) for r in
                        Rate.query.order_by(desc(Rate.valid_from)).all()]
    letter_rates = [(r.start_date, r.crown, r.sheet_count, r.rate) for r in
                    LetterRate.query.order_by(desc(LetterRate.start_date)).all()]

    rate = get_rate(non_letter_rates, letter_rates, SMS_TYPE, datetime(2018, 1, 1))
    assert rate == Decimal(0.15)

    rate = get_rate(non_letter_rates, letter_rates, EMAIL_TYPE, datetime(2018, 1, 1))
    assert rate == Decimal(0)
