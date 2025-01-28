from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from freezegun import freeze_time

from app.celery.reporting_tasks import (
    create_nightly_billing,
    create_nightly_notification_status,
    create_nightly_notification_status_for_service_and_day,
    create_or_update_ft_billing_for_day,
    create_or_update_ft_billing_letter_despatch_for_day,
)
from app.config import QueueNames
from app.constants import (
    EMAIL_TYPE,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEAM,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_TYPES,
    SMS_TYPE,
)
from app.dao.fact_billing_dao import get_rate
from app.models import FactBilling, FactNotificationStatus, Notification
from tests.app.db import (
    create_letter_rate,
    create_notification,
    create_notification_history,
    create_rate,
    create_service,
    create_template,
)


def mocker_get_rate(
    non_letter_rates, letter_rates, notification_type, bst_date, crown=None, rate_multiplier=None, post_class="second"
):
    if notification_type == LETTER_TYPE:
        return Decimal(2.1)
    elif notification_type == SMS_TYPE:
        return Decimal(1.33)
    elif notification_type == EMAIL_TYPE:
        return Decimal(0)


@freeze_time("2019-08-01")
@pytest.mark.parametrize(
    "day_start, expected_kwargs",
    [
        (None, [f"2019-07-{31 - i}" for i in range(10)]),
        ("2019-07-21", [f"2019-07-{21 - i}" for i in range(10)]),
    ],
)
def test_create_nightly_billing_triggers_tasks_for_days(notify_api, mock_celery_task, day_start, expected_kwargs):
    mock_ft_billing = mock_celery_task(create_or_update_ft_billing_for_day)
    mock_ft_billing_letter_despatch = mock_celery_task(create_or_update_ft_billing_letter_despatch_for_day)
    create_nightly_billing(day_start)

    for mock in [mock_ft_billing, mock_ft_billing_letter_despatch]:
        assert mock.call_count == 10
        for i in range(10):
            assert mock.call_args_list[i][1]["kwargs"] == {"process_day": expected_kwargs[i]}


@freeze_time("2019-08-01T00:30")
def test_create_nightly_notification_status_triggers_tasks(
    sample_service,
    sample_template,
    mock_celery_task,
):
    mock_celery = mock_celery_task(create_nightly_notification_status_for_service_and_day)

    create_notification(template=sample_template, created_at="2019-07-31")
    create_nightly_notification_status()

    mock_celery.assert_called_with(
        kwargs={"service_id": sample_service.id, "process_day": "2019-07-31", "notification_type": SMS_TYPE},
        queue=QueueNames.REPORTING,
    )


@freeze_time("2019-08-01T00:30")
@pytest.mark.parametrize(
    "notification_date, expected_types_aggregated",
    [
        ("2019-08-01", set()),
        ("2019-07-31", {EMAIL_TYPE, SMS_TYPE, LETTER_TYPE}),
        ("2019-07-28", {EMAIL_TYPE, SMS_TYPE, LETTER_TYPE}),
        ("2019-07-27", {LETTER_TYPE}),
        ("2019-07-22", {LETTER_TYPE}),
        ("2019-07-21", set()),
    ],
)
def test_create_nightly_notification_status_triggers_relevant_tasks(
    sample_service,
    mock_celery_task,
    notification_date,
    expected_types_aggregated,
):
    mock_celery = mock_celery_task(create_nightly_notification_status_for_service_and_day)

    for notification_type in NOTIFICATION_TYPES:
        template = create_template(sample_service, template_type=notification_type)
        create_notification(template=template, created_at=notification_date)

    create_nightly_notification_status()

    types = {call.kwargs["kwargs"]["notification_type"] for call in mock_celery.mock_calls}
    assert types == expected_types_aggregated


def test_create_or_update_ft_billing_for_day_checks_history(sample_service, sample_letter_template, mocker):
    yesterday = datetime.now() - timedelta(days=1)
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status="sending",
    )

    create_notification_history(
        created_at=yesterday,
        template=sample_letter_template,
        status="delivered",
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_or_update_ft_billing_for_day(str(yesterday.date()))
    records = FactBilling.query.all()
    assert len(records) == 1

    record = records[0]
    assert record.notification_type == LETTER_TYPE
    assert record.notifications_sent == 2


@pytest.mark.parametrize(
    "second_rate, records_num, billable_units, multiplier", [(1.0, 1, 2, [1]), (2.0, 2, 1, [1, 2])]
)
def test_create_or_update_ft_billing_for_day_sms_rate_multiplier(
    sample_service, sample_template, mocker, second_rate, records_num, billable_units, multiplier
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    # These are sms notifications
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status="delivered",
        sent_by="mmg",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status="delivered",
        sent_by="mmg",
        international=False,
        rate_multiplier=second_rate,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_or_update_ft_billing_for_day(str(yesterday.date()))
    records = FactBilling.query.order_by("rate_multiplier").all()
    assert len(records) == records_num

    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == billable_units
        assert record.rate_multiplier == multiplier[i]


def test_create_or_update_ft_billing_for_day_different_templates(
    sample_service, sample_template, sample_email_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status="delivered",
        sent_by="mmg",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_email_template,
        status="delivered",
        sent_by="ses",
        international=False,
        rate_multiplier=0,
        billable_units=0,
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    create_or_update_ft_billing_for_day(str(yesterday.date()))

    records = FactBilling.query.order_by("rate_multiplier").all()
    assert len(records) == 2
    multiplier = [0, 1]
    billable_units = [0, 1]
    rate = [0, Decimal(1.33)]

    for i, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == rate[i]
        assert record.billable_units == billable_units[i]
        assert record.rate_multiplier == multiplier[i]


def test_create_or_update_ft_billing_for_day_different_sent_by(
    sample_service, sample_template, sample_email_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    # These are sms notifications
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status="delivered",
        sent_by="mmg",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )
    create_notification(
        created_at=yesterday,
        template=sample_template,
        status="delivered",
        sent_by="firetext",
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    create_or_update_ft_billing_for_day(str(yesterday.date()))

    records = FactBilling.query.order_by("rate_multiplier").all()
    assert len(records) == 2

    for _, record in enumerate(records):
        assert record.bst_date == datetime.date(yesterday)
        assert record.rate == Decimal(1.33)
        assert record.billable_units == 1
        assert record.rate_multiplier == 1.0


def test_create_or_update_ft_billing_for_day_different_letter_postage(
    notify_db_session, sample_letter_template, mocker
):
    yesterday = datetime.now() - timedelta(days=1)
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    for _ in range(2):
        create_notification(
            created_at=yesterday,
            template=sample_letter_template,
            status="delivered",
            sent_by="dvla",
            billable_units=2,
            postage="first",
        )
    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status="delivered",
        sent_by="dvla",
        billable_units=2,
        postage="second",
    )
    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status="delivered",
        sent_by="dvla",
        billable_units=1,
        postage="europe",
    )
    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status="delivered",
        sent_by="dvla",
        billable_units=3,
        postage="rest-of-world",
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    create_or_update_ft_billing_for_day(str(yesterday.date()))

    records = FactBilling.query.order_by("postage").all()
    assert len(records) == 4

    assert records[0].notification_type == LETTER_TYPE
    assert records[0].bst_date == datetime.date(yesterday)
    assert records[0].postage == "europe"
    assert records[0].notifications_sent == 1
    assert records[0].billable_units == 1

    assert records[1].notification_type == LETTER_TYPE
    assert records[1].bst_date == datetime.date(yesterday)
    assert records[1].postage == "first"
    assert records[1].notifications_sent == 2
    assert records[1].billable_units == 4

    assert records[2].notification_type == LETTER_TYPE
    assert records[2].bst_date == datetime.date(yesterday)
    assert records[2].postage == "rest-of-world"
    assert records[2].notifications_sent == 1
    assert records[2].billable_units == 3

    assert records[3].notification_type == LETTER_TYPE
    assert records[3].bst_date == datetime.date(yesterday)
    assert records[3].postage == "second"
    assert records[3].notifications_sent == 1
    assert records[3].billable_units == 2


def test_create_or_update_ft_billing_for_day_letter(sample_service, sample_letter_template, mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_letter_template,
        status="delivered",
        sent_by="dvla",
        international=False,
        rate_multiplier=2.0,
        billable_units=2,
    )

    records = FactBilling.query.all()
    assert len(records) == 0
    create_or_update_ft_billing_for_day(str(yesterday.date()))

    records = FactBilling.query.order_by("rate_multiplier").all()
    assert len(records) == 1

    record = records[0]
    assert record.notification_type == LETTER_TYPE
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(2.1)
    assert record.billable_units == 2
    assert record.rate_multiplier == 2.0


def test_create_or_update_ft_billing_for_day_null_sent_by_sms(sample_service, sample_template, mocker):
    yesterday = datetime.now() - timedelta(days=1)

    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=yesterday,
        template=sample_template,
        status="delivered",
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_or_update_ft_billing_for_day(str(yesterday.date()))
    records = FactBilling.query.all()
    assert len(records) == 1

    record = records[0]
    assert record.bst_date == datetime.date(yesterday)
    assert record.rate == Decimal(1.33)
    assert record.billable_units == 1
    assert record.rate_multiplier == 1
    assert record.provider == "unknown"


def test_get_rate_for_letter_latest(notify_db_session):
    # letter rates should be passed into the get_rate function as a tuple of start_date, crown, sheet_count,
    # rate and post_class
    new = create_letter_rate(datetime(2017, 12, 1), crown=True, sheet_count=1, rate=0.33, post_class="second")
    old = create_letter_rate(datetime(2016, 12, 1), crown=True, sheet_count=1, rate=0.30, post_class="second")
    letter_rates = [new, old]

    rate = get_rate([], letter_rates, LETTER_TYPE, date(2018, 1, 1), True, 1)
    assert rate == Decimal("0.33")


def test_get_rate_for_letter_latest_if_crown_is_none(notify_db_session):
    # letter rates should be passed into the get_rate function as a tuple of start_date, crown, sheet_count,
    # rate and post_class
    crown = create_letter_rate(datetime(2017, 12, 1), crown=True, sheet_count=1, rate=0.33, post_class="second")
    non_crown = create_letter_rate(datetime(2017, 12, 1), crown=False, sheet_count=1, rate=0.35, post_class="second")
    letter_rates = [crown, non_crown]

    rate = get_rate([], letter_rates, LETTER_TYPE, date(2018, 1, 1), crown=None, letter_page_count=1)
    assert rate == Decimal("0.33")


def test_get_rate_for_sms_and_email(notify_db_session):
    non_letter_rates = [
        create_rate(datetime(2017, 12, 1), 0.15, SMS_TYPE),
        create_rate(datetime(2017, 12, 1), 0, EMAIL_TYPE),
    ]

    rate = get_rate(non_letter_rates, [], SMS_TYPE, date(2018, 1, 1))
    assert rate == Decimal(0.15)

    rate = get_rate(non_letter_rates, [], EMAIL_TYPE, date(2018, 1, 1))
    assert rate == Decimal(0)


@freeze_time("2018-03-30T01:00:00")
# summer time starts on 2018-03-25
def test_create_or_update_ft_billing_for_day_use_BST(sample_service, sample_template, mocker):
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    # too late
    create_notification(
        created_at=datetime(2018, 3, 25, 23, 1),
        template=sample_template,
        status="delivered",
        rate_multiplier=1.0,
        billable_units=1,
    )

    create_notification(
        created_at=datetime(2018, 3, 25, 22, 59),
        template=sample_template,
        status="delivered",
        rate_multiplier=1.0,
        billable_units=2,
    )

    # too early
    create_notification(
        created_at=datetime(2018, 3, 24, 23, 59),
        template=sample_template,
        status="delivered",
        rate_multiplier=1.0,
        billable_units=4,
    )

    assert Notification.query.count() == 3
    assert FactBilling.query.count() == 0

    create_or_update_ft_billing_for_day("2018-03-25")
    records = FactBilling.query.order_by(FactBilling.bst_date).all()

    assert len(records) == 1
    assert records[0].bst_date == date(2018, 3, 25)
    assert records[0].billable_units == 2


@freeze_time("2018-01-15T03:30:00")
def test_create_or_update_ft_billing_for_day_update_when_record_exists(sample_service, sample_template, mocker):
    mocker.patch("app.dao.fact_billing_dao.get_rate", side_effect=mocker_get_rate)

    create_notification(
        created_at=datetime.now() - timedelta(days=1),
        template=sample_template,
        status="delivered",
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    records = FactBilling.query.all()
    assert len(records) == 0

    create_or_update_ft_billing_for_day("2018-01-14")
    records = FactBilling.query.order_by(FactBilling.bst_date).all()

    assert len(records) == 1
    assert records[0].bst_date == date(2018, 1, 14)
    assert records[0].billable_units == 1
    assert not records[0].updated_at

    create_notification(
        created_at=datetime.now() - timedelta(days=1),
        template=sample_template,
        status="delivered",
        sent_by=None,
        international=False,
        rate_multiplier=1.0,
        billable_units=1,
    )

    # run again, make sure create_nightly_billing() updates with no error
    create_or_update_ft_billing_for_day("2018-01-14")
    assert len(records) == 1
    assert records[0].billable_units == 2
    assert records[0].updated_at


def test_create_nightly_notification_status_for_service_and_day(notify_db_session):
    first_service = create_service(service_name="First Service")
    first_template = create_template(service=first_service)
    second_service = create_service(service_name="second Service")
    second_template = create_template(service=second_service, template_type="email")
    third_template = create_template(service=second_service, template_type="letter")

    process_day = date.today() - timedelta(days=5)
    with freeze_time(datetime.combine(process_day, time.min)):
        create_notification(template=first_template, status="delivered")
        create_notification(template=second_template, status="temporary-failure")

        # team API key notifications are included
        create_notification(template=third_template, status="sending", key_type=KEY_TYPE_TEAM)

        # test notifications are ignored
        create_notification(template=third_template, status="sending", key_type=KEY_TYPE_TEST)

        # historical notifications are included
        create_notification_history(template=third_template, status="delivered")

    # these created notifications from a different day get ignored
    with freeze_time(datetime.combine(date.today() - timedelta(days=4), time.min)):
        create_notification(template=first_template)
        create_notification_history(template=second_template)
        create_notification(template=third_template)

    assert len(FactNotificationStatus.query.all()) == 0

    create_nightly_notification_status_for_service_and_day(str(process_day), first_service.id, "sms")
    create_nightly_notification_status_for_service_and_day(str(process_day), second_service.id, "email")
    create_nightly_notification_status_for_service_and_day(str(process_day), second_service.id, "letter")

    new_fact_data = FactNotificationStatus.query.order_by(
        FactNotificationStatus.notification_type,
        FactNotificationStatus.notification_status,
    ).all()

    assert len(new_fact_data) == 4

    email_failure_row = new_fact_data[0]
    assert email_failure_row.bst_date == process_day
    assert email_failure_row.template_id == second_template.id
    assert email_failure_row.service_id == second_service.id
    assert email_failure_row.job_id == UUID("00000000-0000-0000-0000-000000000000")
    assert email_failure_row.notification_type == "email"
    assert email_failure_row.notification_status == "temporary-failure"
    assert email_failure_row.notification_count == 1
    assert email_failure_row.key_type == KEY_TYPE_NORMAL

    letter_delivered_row = new_fact_data[1]
    assert letter_delivered_row.template_id == third_template.id
    assert letter_delivered_row.service_id == second_service.id
    assert letter_delivered_row.notification_type == "letter"
    assert letter_delivered_row.notification_status == "delivered"
    assert letter_delivered_row.notification_count == 1
    assert letter_delivered_row.key_type == KEY_TYPE_NORMAL

    letter_sending_row = new_fact_data[2]
    assert letter_sending_row.template_id == third_template.id
    assert letter_sending_row.service_id == second_service.id
    assert letter_sending_row.notification_type == "letter"
    assert letter_sending_row.notification_status == "sending"
    assert letter_sending_row.notification_count == 1
    assert letter_sending_row.key_type == KEY_TYPE_TEAM

    sms_delivered_row = new_fact_data[3]
    assert sms_delivered_row.template_id == first_template.id
    assert sms_delivered_row.service_id == first_service.id
    assert sms_delivered_row.notification_type == "sms"
    assert sms_delivered_row.notification_status == "delivered"
    assert sms_delivered_row.notification_count == 1
    assert sms_delivered_row.key_type == KEY_TYPE_NORMAL


def test_create_nightly_notification_status_for_service_and_day_overwrites_old_data(notify_db_session):
    first_service = create_service(service_name="First Service")
    first_template = create_template(service=first_service)
    process_day = date.today()

    # first run: one notification, expect one row (just one status)
    notification = create_notification(template=first_template, status="sending")
    create_nightly_notification_status_for_service_and_day(str(process_day), first_service.id, "sms")

    new_fact_data = FactNotificationStatus.query.all()

    assert len(new_fact_data) == 1
    assert new_fact_data[0].notification_count == 1
    assert new_fact_data[0].notification_status == "sending"

    # second run: status changed, still expect one row (one status)
    notification.status = "delivered"
    create_notification(template=first_template, status="created")
    create_nightly_notification_status_for_service_and_day(str(process_day), first_service.id, "sms")

    updated_fact_data = FactNotificationStatus.query.order_by(FactNotificationStatus.notification_status).all()

    assert len(updated_fact_data) == 2
    assert updated_fact_data[0].notification_count == 1
    assert updated_fact_data[0].notification_status == "created"
    assert updated_fact_data[1].notification_count == 1
    assert updated_fact_data[1].notification_status == "delivered"


# the job runs at 12:30am London time. 04/01 is in BST.
@freeze_time("2019-04-01T23:30")
def test_create_nightly_notification_status_for_service_and_day_respects_bst(sample_template):
    create_notification(sample_template, status="delivered", created_at=datetime(2019, 4, 1, 23, 0))  # too new

    create_notification(sample_template, status="created", created_at=datetime(2019, 4, 1, 22, 59))
    create_notification(sample_template, status="created", created_at=datetime(2019, 3, 31, 23, 0))

    create_notification(sample_template, status="delivered", created_at=datetime(2019, 3, 31, 22, 59))  # too old

    create_nightly_notification_status_for_service_and_day("2019-04-01", sample_template.service_id, "sms")

    noti_status = FactNotificationStatus.query.order_by(FactNotificationStatus.bst_date).all()
    assert len(noti_status) == 1

    assert noti_status[0].bst_date == date(2019, 4, 1)
    assert noti_status[0].notification_status == "created"
