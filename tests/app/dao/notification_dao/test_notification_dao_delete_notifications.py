import uuid
from datetime import UTC, datetime, timedelta

import boto3
import pytest
from flask import current_app
from freezegun import freeze_time
from moto import mock_s3

from app.constants import KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST
from app.dao.notifications_dao import (
    FIELDS_TO_TRANSFER_TO_NOTIFICATION_HISTORY,
    insert_notification_history_delete_notifications,
    move_notifications_to_notification_history,
)
from app.models import Notification, NotificationHistory
from tests.app.db import (
    create_notification,
    create_notification_history,
    create_service,
    create_template,
)


def test_every_column_in_notification_history_is_filled_with_data_from_notifications():
    # This test is there to prevent the case where we add a new column to notifications and notifications_history but
    # forget to update our code to copy the data in that new column across to the notificataions_history table every
    # night
    assert len(FIELDS_TO_TRANSFER_TO_NOTIFICATION_HISTORY) == len(NotificationHistory.__table__.columns.keys())


@mock_s3
@freeze_time("2019-09-01 04:30")
def test_move_notifications_deletes_letters_from_s3(sample_letter_template, mocker):
    s3 = boto3.client("s3", region_name="eu-west-1")
    bucket_name = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    eight_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8)
    create_notification(
        template=sample_letter_template,
        status="delivered",
        reference="LETTER_REF",
        created_at=eight_days_ago,
        sent_at=eight_days_ago,
    )
    filename = "{}/NOTIFY.LETTER_REF.D.2.C.{}.PDF".format(
        str(eight_days_ago.date()), eight_days_ago.strftime("%Y%m%d%H%M%S")
    )
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b"foo")

    move_notifications_to_notification_history("letter", sample_letter_template.service_id, datetime(2020, 1, 2))

    with pytest.raises(s3.exceptions.NoSuchKey):
        s3.get_object(Bucket=bucket_name, Key=filename)


@mock_s3
@freeze_time("2019-09-01 04:30")
def test_move_notifications_copes_if_letter_not_in_s3(sample_letter_template, mocker):
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(
        Bucket=current_app.config["S3_BUCKET_LETTERS_PDF"],
        CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
    )

    eight_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8)
    create_notification(template=sample_letter_template, status="delivered", sent_at=eight_days_ago)

    move_notifications_to_notification_history("letter", sample_letter_template.service_id, datetime(2020, 1, 2))
    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1


def test_move_notifications_does_nothing_if_notification_history_row_already_exists(sample_email_template, mocker):
    notification = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8),
        status="temporary-failure",
    )
    create_notification_history(
        id=notification.id,
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8),
        status="delivered",
    )

    move_notifications_to_notification_history(
        "email", sample_email_template.service_id, datetime.now(UTC).replace(tzinfo=None), 1
    )

    assert Notification.query.count() == 0
    history = NotificationHistory.query.all()
    assert len(history) == 1
    assert history[0].status == "delivered"


@pytest.mark.parametrize("notification_status", ["validation-failed", "virus-scan-failed"])
def test_move_notifications_deletes_letters_not_sent_and_in_final_state_from_table_but_not_s3(
    sample_service, mocker, notification_status
):
    mock_s3_object = mocker.patch("app.dao.notifications_dao.find_letter_pdf_in_s3").return_value
    letter_template = create_template(service=sample_service, template_type="letter")
    create_notification(
        template=letter_template,
        status=notification_status,
        reference="LETTER_REF",
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=14),
    )
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    move_notifications_to_notification_history("letter", sample_service.id, datetime.now(UTC).replace(tzinfo=None))

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1
    mock_s3_object.assert_not_called()


@mock_s3
@freeze_time("2020-12-24 04:30")
@pytest.mark.parametrize("notification_status", ["delivered", "returned-letter", "technical-failure"])
def test_move_notifications_deletes_letters_sent_and_in_final_state_from_table_and_s3(
    sample_service, mocker, notification_status
):
    bucket_name = current_app.config["S3_BUCKET_LETTERS_PDF"]
    s3 = boto3.client("s3", region_name="eu-west-1")
    s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": "eu-west-1"})

    letter_template = create_template(service=sample_service, template_type="letter")
    eight_days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8)
    create_notification(
        template=letter_template,
        status=notification_status,
        reference="LETTER_REF",
        created_at=eight_days_ago,
        sent_at=eight_days_ago,
    )
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    filename = "{}/NOTIFY.LETTER_REF.D.2.C.{}.PDF".format(
        str(eight_days_ago.date()), eight_days_ago.strftime("%Y%m%d%H%M%S")
    )
    s3.put_object(Bucket=bucket_name, Key=filename, Body=b"foo")

    move_notifications_to_notification_history("letter", sample_service.id, datetime.now(UTC).replace(tzinfo=None))

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 1

    with pytest.raises(s3.exceptions.NoSuchKey):
        s3.get_object(Bucket=bucket_name, Key=filename)


@pytest.mark.parametrize("notification_status", ["pending-virus-check", "created", "sending"])
def test_move_notifications_does_not_delete_letters_not_yet_in_final_state(sample_service, mocker, notification_status):
    mock_s3_object = mocker.patch("app.dao.notifications_dao.find_letter_pdf_in_s3").return_value
    letter_template = create_template(service=sample_service, template_type="letter")
    create_notification(
        template=letter_template,
        status=notification_status,
        reference="LETTER_REF",
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8),
    )
    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0

    move_notifications_to_notification_history("letter", sample_service.id, datetime.now(UTC).replace(tzinfo=None))

    assert Notification.query.count() == 1
    assert NotificationHistory.query.count() == 0
    mock_s3_object.assert_not_called()


def test_move_notifications_only_moves_notifications_older_than_provided_timestamp(sample_template):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)
    one_second_after = delete_time + timedelta(seconds=1)
    old_notification = create_notification(template=sample_template, created_at=one_second_before)
    new_notification = create_notification(template=sample_template, created_at=one_second_after)

    # need to take a copy of the ID since the old_notification object will stop being accessible once removed
    old_notification_id = old_notification.id

    result = move_notifications_to_notification_history("sms", sample_template.service_id, delete_time)
    assert result == 1

    assert Notification.query.one().id == new_notification.id
    assert NotificationHistory.query.one().id == old_notification_id


def test_move_notifications_keeps_calling_until_no_more_to_delete_and_then_returns_total_deleted(
    notify_db_session, mocker
):
    mock_insert = mocker.patch(
        "app.dao.notifications_dao.insert_notification_history_delete_notifications", side_effect=[5, 5, 1, 0]
    )
    service_id = uuid.uuid4()
    timestamp = datetime(2021, 1, 1)

    result = move_notifications_to_notification_history("sms", service_id, timestamp, qry_limit=5)
    assert result == 11

    mock_insert.assert_called_with(
        notification_type="sms", service_id=service_id, timestamp_to_delete_backwards_from=timestamp, qry_limit=5
    )
    assert mock_insert.call_count == 4


def test_move_notifications_only_moves_for_given_notification_type(sample_service):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)

    sms_template = create_template(sample_service, "sms")
    email_template = create_template(sample_service, "email")
    letter_template = create_template(sample_service, "letter")
    create_notification(sms_template, created_at=one_second_before)
    create_notification(email_template, created_at=one_second_before)
    create_notification(letter_template, created_at=one_second_before)

    result = move_notifications_to_notification_history("sms", sample_service.id, delete_time)
    assert result == 1
    assert {x.notification_type for x in Notification.query} == {"email", "letter"}
    assert NotificationHistory.query.one().notification_type == "sms"


def test_move_notifications_only_moves_for_given_service(notify_db_session):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)

    service = create_service(service_name="service")
    other_service = create_service(service_name="other")

    template = create_template(service, "sms")
    other_template = create_template(other_service, "sms")

    create_notification(template, created_at=one_second_before)
    create_notification(other_template, created_at=one_second_before)

    result = move_notifications_to_notification_history("sms", service.id, delete_time)
    assert result == 1

    assert NotificationHistory.query.one().service_id == service.id
    assert Notification.query.one().service_id == other_service.id


def test_move_notifications_just_deletes_test_key_notifications(sample_template):
    delete_time = datetime(2020, 6, 1, 12)
    one_second_before = delete_time - timedelta(seconds=1)
    create_notification(template=sample_template, created_at=one_second_before, key_type=KEY_TYPE_NORMAL)
    create_notification(template=sample_template, created_at=one_second_before, key_type=KEY_TYPE_TEAM)
    create_notification(template=sample_template, created_at=one_second_before, key_type=KEY_TYPE_TEST)

    result = move_notifications_to_notification_history("sms", sample_template.service_id, delete_time)

    assert result == 2

    assert Notification.query.count() == 0
    assert NotificationHistory.query.count() == 2
    assert NotificationHistory.query.filter(NotificationHistory.key_type == KEY_TYPE_TEST).count() == 0


@freeze_time("2020-03-20 14:00")
def test_insert_notification_history_delete_notifications(sample_email_template):
    # should be deleted
    n1 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, minutes=4),
        status="delivered",
    )
    n2 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, minutes=20),
        status="permanent-failure",
    )
    n3 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, minutes=30),
        status="temporary-failure",
    )
    n4 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, minutes=59),
        status="temporary-failure",
    )
    n5 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, hours=1),
        status="sending",
    )
    n6 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, minutes=61),
        status="pending",
    )
    n7 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, hours=1, seconds=1),
        status="validation-failed",
    )
    n8 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1, minutes=20),
        status="created",
    )
    # should NOT be deleted - wrong status
    n9 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
        status="delivered",
    )
    n10 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1),
        status="technical-failure",
    )
    n11 = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=23, minutes=59),
        status="created",
    )

    ids_to_move = sorted([n1.id, n2.id, n3.id, n4.id, n5.id, n6.id, n7.id, n8.id])
    ids_to_keep = sorted([n9.id, n10.id, n11.id])
    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_email_template.template_type,
        service_id=sample_email_template.service_id,
        timestamp_to_delete_backwards_from=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
    )
    assert del_count == 8
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(history_rows) == 8
    assert ids_to_move == sorted([x.id for x in history_rows])
    assert len(notifications) == 3
    assert ids_to_keep == sorted([x.id for x in notifications])


def test_insert_notification_history_delete_notifications_more_notifications_than_query_limit(sample_template):
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=4),
        status="delivered",
    )
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=20),
        status="permanent-failure",
    )
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30),
        status="temporary-failure",
    )

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_template.template_type,
        service_id=sample_template.service_id,
        timestamp_to_delete_backwards_from=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        qry_limit=1,
    )

    assert del_count == 1
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(history_rows) == 1
    assert len(notifications) == 2


def test_insert_notification_history_delete_notifications_only_insert_delete_for_given_service(sample_email_template):
    notification_to_move = create_notification(
        template=sample_email_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=4),
        status="delivered",
    )
    another_service = create_service(service_name="Another service")
    another_template = create_template(service=another_service, template_type="email")
    notification_to_stay = create_notification(
        template=another_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=4),
        status="delivered",
    )

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_email_template.template_type,
        service_id=sample_email_template.service_id,
        timestamp_to_delete_backwards_from=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
    )

    assert del_count == 1
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(notifications) == 1
    assert len(history_rows) == 1
    assert notifications[0].id == notification_to_stay.id
    assert history_rows[0], id == notification_to_move.id


def test_insert_notification_history_delete_notifications_insert_for_key_type(sample_template):
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=4),
        status="delivered",
        key_type="normal",
    )
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=4),
        status="delivered",
        key_type="team",
    )
    with_test_key = create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=4),
        status="delivered",
        key_type="test",
    )

    del_count = insert_notification_history_delete_notifications(
        notification_type=sample_template.template_type,
        service_id=sample_template.service_id,
        timestamp_to_delete_backwards_from=datetime.now(UTC).replace(tzinfo=None),
    )

    assert del_count == 2
    notifications = Notification.query.all()
    history_rows = NotificationHistory.query.all()
    assert len(notifications) == 1
    assert with_test_key.id == notifications[0].id
    assert len(history_rows) == 2


def test_insert_notification_history_delete_notifications_can_handle_different_column_orders(
    sample_template, notify_db_session
):
    """Validate that the notification->history process can handle the history table's columns being in a different
    order to the notification/notification_archive table - ie that we are explicitly saying which columns we are taking
    from and where we are inserting into.

    This is because our prod->staging migrate+anonymise process sometimes drops+recreates columns, which will have
    them in a different order:

    https://github.com/alphagov/notifications-aws/blob/main/scripts/remove-all-sensitive-and-personal-data/
    remove-all-sensitive-and-personal-data-part-2.sql
    """
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=4),
        status="delivered",
        key_type="normal",
    )
    create_notification(
        template=sample_template,
        created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=4),
        status="delivered",
        key_type="team",
    )

    with notify_db_session.begin_nested():
        notify_db_session.execute("drop view notifications_all_time_view")
        notify_db_session.execute("alter table notification_history drop column client_reference")
        notify_db_session.execute("alter table notification_history add column client_reference varchar")

        del_count = insert_notification_history_delete_notifications(
            notification_type=sample_template.template_type,
            service_id=sample_template.service_id,
            timestamp_to_delete_backwards_from=datetime.now(UTC).replace(tzinfo=None),
        )

        assert del_count == 2

        # Restore the view and undo column changes.
        notify_db_session.rollback()
