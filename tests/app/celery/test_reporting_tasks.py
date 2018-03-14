from datetime import datetime, timedelta
from tests.app.conftest import sample_notification
from app.celery.reporting_tasks import create_nightly_billing, get_rate
from app.models import FactBilling
from decimal import Decimal
import pytest
from app.dao.letter_rate_dao import dao_create_letter_rate
from app.models import LetterRate, Rate
from app import db


def test_reporting_should_have_decorated_tasks_functions():
    assert create_nightly_billing.__wrapped__.__name__ == 'create_nightly_billing'


def mocker_get_rate(notification_type, date, crown=None, rate_multiplier=None):
    if notification_type == 'letter':
        return Decimal(2.1)
    elif notification_type == 'sms':
        return Decimal(1.33)
    elif notification_type == 'email':
        return Decimal(0)


# Test when notifications with all dimensions are the same, and when the rate is different
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
    # two_days_ago = datetime.now() - timedelta(days=6)

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
    # before running migration no records
    records = FactBilling.query.all()
    assert len(records) == 0
    # before record data after migration
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
    # two_days_ago = datetime.now() - timedelta(days=6)

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
        template=sample_email_template,
        status='delivered',
        sent_by='ses',
        international=False,
        rate_multiplier=0,
        billable_units=0,
    )
    # before running migration no records
    records = FactBilling.query.all()
    assert len(records) == 0
    # before record data after migration
    create_nightly_billing(yesterday)
    records = FactBilling.query.order_by('rate_multiplier').all()
    # First record is ses and second record is sms
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
    # two_days_ago = datetime.now() - timedelta(days=6)

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
    # before running migration no records
    records = FactBilling.query.all()
    assert len(records) == 0
    # before record data after migration
    create_nightly_billing(yesterday)
    records = FactBilling.query.order_by('rate_multiplier').all()
    # First record is ses and second record is sms
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
    # two_days_ago = datetime.now() - timedelta(days=6)

    # These are sms notifications
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

    # before running migration no records
    records = FactBilling.query.all()
    assert len(records) == 0
    # before record data after migration
    create_nightly_billing(yesterday)
    records = FactBilling.query.order_by('rate_multiplier').all()
    assert len(records) == 1
    record = records[0]
    assert record.notification_type == 'letter'
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
    # two_days_ago = datetime.now() - timedelta(days=6)

    # These are sms notifications
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

    # before running migration no records
    records = FactBilling.query.all()
    assert len(records) == 0
    # before record data after migration
    create_nightly_billing(yesterday)
    records = FactBilling.query.all()
    # First record is ses and second record is sms
    assert len(records) == 1
    record = records[0]
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(1.33)
    assert record.billable_units == 1
    assert record.rate_multiplier == 1
    assert record.provider in ['mmg', 'firetext']


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

    rate = get_rate('letter', datetime(2018, 1, 1), True, 1)
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
                    notification_type='sms')
    db.session.add(sms_rate)
    email_rate = Rate(valid_from=datetime(2017, 12, 1),
                      rate=Decimal(0),
                      notification_type='email')
    db.session.add(email_rate)

    rate = get_rate('sms', datetime(2018, 1, 1))
    assert rate == Decimal(0.15)

    rate = get_rate('email', datetime(2018, 1, 1))
    assert rate == Decimal(0)
