from datetime import datetime, timedelta, date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from app.celery.reporting_tasks import create_nightly_billing, create_nightly_notification_status
from app.dao.fact_billing_dao import get_rate
from app.models import (
    FactBilling,
    Notification,
    LETTER_TYPE,
    EMAIL_TYPE,
    SMS_TYPE, FactNotificationStatus
)

from tests.app.db import create_service, create_template, create_notification, create_rate, create_letter_rate


def mocker_get_rate(
    non_letter_rates, letter_rates, notification_type, bst_date, crown=None, rate_multiplier=None, post_class="second"
):
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
        sample_service,
        sample_template,
        mocker,
        second_rate,
        records_num,
        billable_units,
        multiplier):

    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    # These are sms notifications
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=second_rate,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    # Celery expects the arguments to be a string or primitive type.
    yesterday_str = datetime.strftime(yesterday, "%Y-%m-%d")
    create_nightly_billing(yesterday_str)
    records = FactBilling.query.order_by('rate_multiplier').all()
    assert len(records) == records_num
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == billable_units
        assert record.rate_multiplier == multiplier[i]


def test_create_nightly_billing_different_templates(
        sample_service,
        sample_template,
        sample_email_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_email_template,
        status='delivered',
        sent_by='ses',
        international=False,
        rate_multiplier=0,
        billable_units=0,
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    # Celery expects the arguments to be a string or primitive type.
    yesterday_str = datetime.strftime(yesterday, "%Y-%m-%d")
    create_nightly_billing(yesterday_str)
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
        sample_service,
        sample_template,
        sample_email_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    # These are sms notifications
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status='delivered',
        sent_by='mmg',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status='delivered',
        sent_by='firetext',
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    # Celery expects the arguments to be a string or primitive type.
    yesterday_str = datetime.strftime(yesterday, "%Y-%m-%d")
    create_nightly_billing(yesterday_str)
    records = FactBilling.query.order_by('rate_multiplier').all()

    assert len(records) == 2
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == 1
        assert record.rate_multiplier == 1.0


def test_create_nightly_billing_different_letter_postage(
        notify_db_session,
        sample_letter_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)
    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    for i in range(2):
        create_notification(
            created_at=yesterday,
            template=sample_letter_template,
            status='delivered',
            sent_by='dvla',
            billable_units=2,
            postage='first'
        )
    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status='delivered',
        sent_by='dvla',
        billable_units=2,
        postage='second'
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    # Celery expects the arguments to be a string or primitive type.
    yesterday_str = datetime.strftime(yesterday, "%Y-%m-%d")
    create_nightly_billing(yesterday_str)

    records = FactBilling.query.order_by('postage').all()
    assert len(records) == 2
    assert records[0].notification_type == LETTER_TYPE
    assert records[0].bst_date == datetime.date(yesterday)
    assert records[0].postage == 'first'
    assert records[0].notifications_sent == 2
    assert records[0].billable_units == 4

    assert records[1].notification_type == LETTER_TYPE
    assert records[1].bst_date == datetime.date(yesterday)
    assert records[1].postage == 'second'
    assert records[1].notifications_sent == 1
    assert records[1].billable_units == 2


def test_create_nightly_billing_letter(
        sample_service,
        sample_letter_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status='delivered',
        sent_by='dvla',
        international=False,
        rate_multiplier=2.0,
        billable_units=2,
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    # Celery expects the arguments to be a string or primitive type.
    yesterday_str = datetime.strftime(yesterday, "%Y-%m-%d")
    create_nightly_billing(yesterday_str)
    records = FactBilling.query.order_by('rate_multiplier').all()
    assert len(records) == 1
    record = records[0]
    assert record.notification_type == LETTER_TYPE
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(2.1)
    assert record.billable_units == 2
    assert record.rate_multiplier == 2.0


def test_create_nightly_billing_null_sent_by_sms(
        sample_service,
        sample_template,
        mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status='delivered',
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    # Celery expects the arguments to be a string or primitive type.
    yesterday_str = datetime.strftime(yesterday, "%Y-%m-%d")
    create_nightly_billing(yesterday_str)
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
        sample_template,
        mocker):

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    # create records from 11th to 15th
    for i in range(0, 5):
        create_notification(
            created_at=datetime.now() - timedelta(days=i),
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
    assert records[0].bst_date == date(2018, 1, 11)
    assert records[-1].bst_date == date(2018, 1, 14)


def test_get_rate_for_letter_latest(notify_db_session):
    # letter rates should be passed into the get_rate function as a tuple of start_date, crown, sheet_count,
    # rate and post_class
    new = create_letter_rate(datetime(2017, 12, 1), crown=True, sheet_count=1, rate=0.33, post_class='second')
    old = create_letter_rate(datetime(2016, 12, 1), crown=True, sheet_count=1, rate=0.30, post_class='second')
    letter_rates = [new, old]

    rate = get_rate([], letter_rates, LETTER_TYPE, date(2018, 1, 1), True, 1)
    assert rate == Decimal('0.33')


def test_get_rate_for_sms_and_email(notify_db_session):
    non_letter_rates = [
        create_rate(datetime(2017, 12, 1), 0.15, SMS_TYPE),
        create_rate(datetime(2017, 12, 1), 0, EMAIL_TYPE)
    ]

    rate = get_rate(non_letter_rates, [], SMS_TYPE, date(2018, 1, 1))
    assert rate == Decimal(0.15)

    rate = get_rate(non_letter_rates, [], EMAIL_TYPE, date(2018, 1, 1))
    assert rate == Decimal(0)


@freeze_time('2018-03-26T23:30:00')
# summer time starts on 2018-03-25
def test_create_nightly_billing_use_BST(
        sample_service,
        sample_template,
        mocker):

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    create_notification(
        created_at=datetime(2018, 3, 25, 12, 0),
        template=sample_template,
        status='delivered',
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    create_notification(
        created_at=datetime(2018, 3, 25, 23, 5),
        template=sample_template,
        status='delivered',
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    notifications = Notification.query.order_by(Notification.created_at).all()
    assert len(notifications) == 2
    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing()
    records = FactBilling.query.order_by(FactBilling.bst_date).all()

    assert len(records) == 2
    assert records[0].bst_date == date(2018, 3, 25)
    assert records[-1].bst_date == date(2018, 3, 26)


@freeze_time('2018-01-15T03:30:00')
def test_create_nightly_billing_update_when_record_exists(
        sample_service,
        sample_template,
        mocker):

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    create_notification(
        created_at=datetime.now() - timedelta(days=1),
        template=sample_template,
        status='delivered',
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_nightly_billing()
    records = FactBilling.query.order_by(FactBilling.bst_date).all()

    assert len(records) == 1
    assert records[0].bst_date == date(2018, 1, 14)
    assert records[0].billable_units == 1
    assert not records[0].updated_at

    create_notification(
        created_at=datetime.now() - timedelta(days=1),
        template=sample_template,
        status='delivered',
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    # run again, make sure create_nightly_billing() updates with no error
    create_nightly_billing()
    assert len(records) == 1
    assert records[0].billable_units == 2
    assert records[0].updated_at


def test_create_nightly_notification_status(notify_db_session, mocker):
    mocks = [
        mocker.patch('app.celery.reporting_tasks.delete_email_notifications_older_than_retention'),
        mocker.patch('app.celery.reporting_tasks.delete_sms_notifications_older_than_retention'),
        mocker.patch('app.celery.reporting_tasks.delete_letter_notifications_older_than_retention'),
    ]

    first_service = create_service(service_name='First Service')
    first_template = create_template(service=first_service)
    second_service = create_service(service_name='second Service')
    second_template = create_template(service=second_service, template_type='email')
    third_service = create_service(service_name='third Service')
    third_template = create_template(service=third_service, template_type='letter')

    create_notification(template=first_template, status='delivered')
    create_notification(template=first_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=1))
    create_notification(template=first_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=2))
    create_notification(template=first_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=10))
    create_notification(template=first_template, status='delivered', created_at=datetime.utcnow() - timedelta(days=10))

    create_notification(template=second_template, status='temporary-failure')
    create_notification(template=second_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=1))
    create_notification(template=second_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=2))
    create_notification(template=second_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=10))
    create_notification(template=second_template, status='temporary-failure',
                        created_at=datetime.utcnow() - timedelta(days=10))

    create_notification(template=third_template, status='created')
    create_notification(template=third_template, status='created', created_at=datetime.utcnow() - timedelta(days=1))
    create_notification(template=third_template, status='created', created_at=datetime.utcnow() - timedelta(days=2))
    create_notification(template=third_template, status='created', created_at=datetime.utcnow() - timedelta(days=10))
    create_notification(template=third_template, status='created', created_at=datetime.utcnow() - timedelta(days=10))

    assert len(FactNotificationStatus.query.all()) == 0

    create_nightly_notification_status()
    new_data = FactNotificationStatus.query.order_by(
        FactNotificationStatus.bst_date,
        FactNotificationStatus.notification_type
    ).all()
    assert len(new_data) == 9
    assert str(new_data[0].bst_date) == datetime.strftime(datetime.utcnow() - timedelta(days=10), "%Y-%m-%d")
    assert str(new_data[3].bst_date) == datetime.strftime(datetime.utcnow() - timedelta(days=2), "%Y-%m-%d")
    assert str(new_data[6].bst_date) == datetime.strftime(datetime.utcnow() - timedelta(days=1), "%Y-%m-%d")

    for mock in mocks:
        mock.apply_async.assert_called_once_with(queue='periodic-tasks')


# the job runs at 12:30am London time. 04/01 is in BST.
@freeze_time('2019-04-01T23:30')
def test_create_nightly_notification_status_respects_bst(sample_template, mocker):
    mocker.patch('app.celery.reporting_tasks.delete_email_notifications_older_than_retention')
    mocker.patch('app.celery.reporting_tasks.delete_sms_notifications_older_than_retention')
    mocker.patch('app.celery.reporting_tasks.delete_letter_notifications_older_than_retention')

    create_notification(sample_template, status='delivered', created_at=datetime(2019, 4, 1, 23, 0))  # too new

    create_notification(sample_template, status='created', created_at=datetime(2019, 4, 1, 22, 59))
    create_notification(sample_template, status='created', created_at=datetime(2019, 3, 31, 23, 0))

    create_notification(sample_template, status='temporary-failure', created_at=datetime(2019, 3, 31, 22, 59))

    # we create records for last ten days
    create_notification(sample_template, status='sending', created_at=datetime(2019, 3, 29, 0, 0))

    create_notification(sample_template, status='delivered', created_at=datetime(2019, 3, 22, 23, 59))  # too old

    create_nightly_notification_status()

    noti_status = FactNotificationStatus.query.order_by(FactNotificationStatus.bst_date).all()
    assert len(noti_status) == 3

    assert noti_status[0].bst_date == date(2019, 3, 29)
    assert noti_status[0].notification_status == 'sending'

    assert noti_status[1].bst_date == date(2019, 3, 31)
    assert noti_status[1].notification_status == 'temporary-failure'

    assert noti_status[2].bst_date == date(2019, 4, 1)
    assert noti_status[2].notification_status == 'created'
