import itertools
from datetime import datetime, timedelta, date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from app.config import QueueNames
from app.celery.reporting_tasks import (
    create_nightly_billing,
    create_nightly_notification_status,
    create_nightly_billing_for_day,
    create_nightly_notification_status_for_day,
)
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


@freeze_time('2019-08-01')
@pytest.mark.parametrize('day_start, expected_kwargs', [
    (None, ['2019-07-31', '2019-07-30', '2019-07-29', '2019-07-28']),
    ('2019-07-21', ['2019-07-21', '2019-07-20', '2019-07-19', '2019-07-18']),
])
def test_create_nightly_billing_triggers_tasks_for_days(notify_api, mocker, day_start, expected_kwargs):
    mock_celery = mocker.patch('app.celery.reporting_tasks.create_nightly_billing_for_day')
    create_nightly_billing(day_start)

    assert mock_celery.apply_async.call_count == 4
    for i in range(4):
        assert mock_celery.apply_async.call_args_list[i][1]['kwargs'] == {'process_day': expected_kwargs[i]}


@freeze_time('2019-08-01')
def test_create_nightly_notification_status_triggers_tasks_for_days(notify_api, mocker):
    mock_celery = mocker.patch('app.celery.reporting_tasks.create_nightly_notification_status_for_day')
    create_nightly_notification_status()

    assert mock_celery.apply_async.call_count == 4 * 3  # four days, three notification types
    for process_date, notification_type in itertools.product(
        ['2019-07-31', '2019-07-30', '2019-07-29', '2019-07-28'],
        ['sms', 'email', 'letter']
    ):
        mock_celery.apply_async.assert_any_call(
            kwargs={'process_day': process_date, 'notification_type': notification_type},
            queue=QueueNames.REPORTING
        )


@pytest.mark.parametrize('second_rate, records_num, billable_units, multiplier',
                         [(1.0, 1, 2, [1]),
                          (2.0, 2, 1, [1, 2])])
def test_create_nightly_billing_for_day_sms_rate_multiplier(
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
    create_nightly_billing_for_day(yesterday_str)
    records = FactBilling.query.order_by('rate_multiplier').all()
    assert len(records) == records_num
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == billable_units
        assert record.rate_multiplier == multiplier[i]


def test_create_nightly_billing_for_day_different_templates(
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
    create_nightly_billing_for_day(yesterday_str)
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


def test_create_nightly_billing_for_day_different_sent_by(
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
    create_nightly_billing_for_day(yesterday_str)
    records = FactBilling.query.order_by('rate_multiplier').all()

    assert len(records) == 2
    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == 1
        assert record.rate_multiplier == 1.0


def test_create_nightly_billing_for_day_different_letter_postage(
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
    create_nightly_billing_for_day(yesterday_str)

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


def test_create_nightly_billing_for_day_letter(
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
    create_nightly_billing_for_day(yesterday_str)
    records = FactBilling.query.order_by('rate_multiplier').all()
    assert len(records) == 1
    record = records[0]
    assert record.notification_type == LETTER_TYPE
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(2.1)
    assert record.billable_units == 2
    assert record.rate_multiplier == 2.0


def test_create_nightly_billing_for_day_null_sent_by_sms(
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
    create_nightly_billing_for_day(yesterday_str)
    records = FactBilling.query.all()

    assert len(records) == 1
    record = records[0]
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(1.33)
    assert record.billable_units == 1
    assert record.rate_multiplier == 1
    assert record.provider == 'unknown'


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


@freeze_time('2018-03-30T01:00:00')
# summer time starts on 2018-03-25
def test_create_nightly_billing_for_day_use_BST(
        sample_service,
        sample_template,
        mocker):

    mocker.patch('app.dao.fact_billing_dao.get_rate', side_effect=mocker_get_rate)

    # too late
    create_notification(
        created_at=datetime(2018, 3, 25, 23, 1),
        template=sample_template,
        status='delivered',
        rate_multiplier=1.0,
        billable_units=1,
    )

    create_notification(
        created_at=datetime(2018, 3, 25, 22, 59),
        template=sample_template,
        status='delivered',
        rate_multiplier=1.0,
        billable_units=2,
    )

    # too early
    create_notification(
        created_at=datetime(2018, 3, 24, 23, 59),
        template=sample_template,
        status='delivered',
        rate_multiplier=1.0,
        billable_units=4,
    )

    assert Notification.query.count() == 3
    assert FactBilling.query.count() == 0

    create_nightly_billing_for_day('2018-03-25')
    records = FactBilling.query.order_by(FactBilling.bst_date).all()

    assert len(records) == 1
    assert records[0].bst_date == date(2018, 3, 25)
    assert records[0].billable_units == 2


@freeze_time('2018-01-15T03:30:00')
def test_create_nightly_billing_for_day_update_when_record_exists(
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

    create_nightly_billing_for_day('2018-01-14')
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
    create_nightly_billing_for_day('2018-01-14')
    assert len(records) == 1
    assert records[0].billable_units == 2
    assert records[0].updated_at


@freeze_time('2019-01-05')
def test_create_nightly_notification_status_for_day(notify_db_session):
    first_service = create_service(service_name='First Service')
    first_template = create_template(service=first_service)
    second_service = create_service(service_name='second Service')
    second_template = create_template(service=second_service, template_type='email')
    third_service = create_service(service_name='third Service')
    third_template = create_template(service=third_service, template_type='letter')

    create_notification(template=first_template, status='delivered')
    create_notification(template=first_template, status='delivered', created_at=datetime(2019, 1, 1, 12, 0))

    create_notification(template=second_template, status='temporary-failure')
    create_notification(template=second_template, status='temporary-failure', created_at=datetime(2019, 1, 1, 12, 0))

    create_notification(template=third_template, status='created')
    create_notification(template=third_template, status='created', created_at=datetime(2019, 1, 1, 12, 0))

    assert len(FactNotificationStatus.query.all()) == 0

    create_nightly_notification_status_for_day('2019-01-01', 'sms')
    create_nightly_notification_status_for_day('2019-01-01', 'email')
    create_nightly_notification_status_for_day('2019-01-01', 'letter')

    new_data = FactNotificationStatus.query.order_by(FactNotificationStatus.created_at).all()

    assert len(new_data) == 3
    assert new_data[0].bst_date == date(2019, 1, 1)
    assert new_data[1].bst_date == date(2019, 1, 1)
    assert new_data[2].bst_date == date(2019, 1, 1)

    assert new_data[0].notification_type == 'sms'
    assert new_data[1].notification_type == 'email'
    assert new_data[2].notification_type == 'letter'

    assert new_data[0].notification_status == 'delivered'
    assert new_data[1].notification_status == 'temporary-failure'
    assert new_data[2].notification_status == 'created'


# the job runs at 12:30am London time. 04/01 is in BST.
@freeze_time('2019-04-01T23:30')
def test_create_nightly_notification_status_for_day_respects_bst(sample_template):
    create_notification(sample_template, status='delivered', created_at=datetime(2019, 4, 1, 23, 0))  # too new

    create_notification(sample_template, status='created', created_at=datetime(2019, 4, 1, 22, 59))
    create_notification(sample_template, status='created', created_at=datetime(2019, 3, 31, 23, 0))

    create_notification(sample_template, status='delivered', created_at=datetime(2019, 3, 31, 22, 59))  # too old

    create_nightly_notification_status_for_day('2019-04-01', 'sms')

    noti_status = FactNotificationStatus.query.order_by(FactNotificationStatus.bst_date).all()
    assert len(noti_status) == 1

    assert noti_status[0].bst_date == date(2019, 4, 1)
    assert noti_status[0].notification_status == 'created'
