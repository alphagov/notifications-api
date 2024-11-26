from collections import defaultdict
from datetime import date

import pytest
from flask import current_app
from freezegun import freeze_time

from app.celery.service_callback_tasks import send_delivery_status_to_service
from app.celery.tasks import (
    check_billable_units,
    get_billing_date_in_bst_from_filename,
    persist_daily_sorted_letter_counts,
    process_updates_from_file,
    record_daily_sorted_counts,
    update_letter_notifications_statuses,
)
from app.constants import (
    NOTIFICATION_DELIVERED,
    NOTIFICATION_SENDING,
    NOTIFICATION_TEMPORARY_FAILURE,
)
from app.dao.daily_sorted_letter_dao import (
    dao_get_daily_sorted_letter_by_billing_day,
)
from app.exceptions import DVLAException
from app.models import DailySortedLetter, LetterCostThreshold, NotificationHistory, NotificationLetterDespatch
from tests.app.db import (
    create_notification,
    create_notification_history,
    create_service_callback_api,
)
from tests.conftest import set_config


@pytest.fixture
def notification_update():
    """
    Returns an instance of the  NotificationUpdate dataclass to use as the argument
    for the check_billable_units function
    """
    from app.celery.tasks import NotificationUpdate
    from app.models import LetterCostThreshold

    return NotificationUpdate("REFERENCE_ABC", "sent", "1", LetterCostThreshold("sorted"), "2023-03-07")


@pytest.mark.parametrize(
    "invalid_file",
    (
        "ref-foo|Sent|2",
        "ref-foo|Sent|1|Unsorted",
        "ref-foo|Sent|1|Unsorted|2023-01-01|unexpected",
        "ref-foo|Sent|1|Unsorted|2023-01-01\nref-foo|Sent|1|Unsorted|2023-01-01|unexpected",
    ),
)
def test_update_letter_notifications_statuses_raises_for_invalid_format(notify_api, mocker, invalid_file):
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=invalid_file)

    with pytest.raises(DVLAException) as e:
        update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")
    assert "DVLA response file: {} has an invalid format".format("NOTIFY-20170823160812-RSP.TXT") in str(e.value)


def test_update_letter_notification_statuses_when_notification_does_not_exist_updates_notification_history(
    sample_letter_template, mocker
):
    valid_file = "ref-foo|Sent|1|Unsorted|2023-01-12"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)
    notification = create_notification_history(
        sample_letter_template, reference="ref-foo", status=NOTIFICATION_SENDING, billable_units=1
    )

    update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")

    updated_history = NotificationHistory.query.filter_by(id=notification.id).one()
    assert updated_history.status == NOTIFICATION_DELIVERED


def test_update_letter_notification_statuses_when_notification_does_not_exist_creates_letter_despatch_record(
    sample_letter_template, mocker
):
    valid_file = "ref-foo|Sent|1|Unsorted|2023-01-12"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)
    notification = create_notification_history(
        sample_letter_template, reference="ref-foo", status=NOTIFICATION_SENDING, billable_units=1
    )

    update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")

    letter_despatch = NotificationLetterDespatch.query.first()
    assert letter_despatch.notification_id == notification.id
    assert letter_despatch.despatched_on == date(2023, 1, 12)
    assert letter_despatch.cost_threshold == LetterCostThreshold.unsorted


def test_update_letter_notifications_statuses_raises_dvla_exception(notify_api, mocker, sample_letter_template):
    valid_file = "ref-foo|Failed|1|Unsorted|2023-01-12"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)
    create_notification(sample_letter_template, reference="ref-foo", status=NOTIFICATION_SENDING, billable_units=0)

    with pytest.raises(DVLAException) as e:
        update_letter_notifications_statuses(filename="failed.txt")
    failed = ["ref-foo"]
    assert "DVLA response file: {filename} has failed letters with notification.reference {failures}".format(
        filename="failed.txt", failures=failed
    ) in str(e.value)


def test_update_letter_notifications_statuses_calls_with_correct_bucket_location(notify_api, mocker):
    s3_mock = mocker.patch("app.celery.tasks.s3.get_s3_object")

    with set_config(notify_api, "S3_BUCKET_DVLA_RESPONSE", "foo.bar-ftp"):
        update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")
        s3_mock.assert_called_with(current_app.config["S3_BUCKET_DVLA_RESPONSE"], "NOTIFY-20170823160812-RSP.TXT")


def test_update_letter_notifications_statuses_builds_updates_from_content(notify_api, mocker):
    valid_file = "ref-foo|Sent|1|Unsorted|2023-02-23\nref-bar|Sent|2|Sorted|2023-02-22"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)
    update_mock = mocker.patch("app.celery.tasks.process_updates_from_file", wraps=process_updates_from_file)
    mocker.patch("app.celery.tasks.check_billable_units")
    mocker.patch("app.celery.tasks.update_letter_notification")

    update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")

    update_mock.assert_called_with(valid_file, filename="NOTIFY-20170823160812-RSP.TXT")


def test_update_letter_notifications_statuses_creates_letter_despatch_record(
    notify_api, mocker, sample_letter_template
):
    valid_file = "ref-foo|Sent|1|Unsorted|2023-02-23\nref-bar|Sent|2|Sorted|2023-02-22"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)
    notification_bar = create_notification(
        sample_letter_template, reference="ref-bar", status=NOTIFICATION_SENDING, billable_units=1
    )
    notification_foo = create_notification(
        sample_letter_template, reference="ref-foo", status=NOTIFICATION_SENDING, billable_units=1
    )

    update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")

    letter_despatches = NotificationLetterDespatch.query.all()
    assert letter_despatches[0].notification_id == notification_foo.id
    assert letter_despatches[0].despatched_on == date(2023, 2, 23)
    assert letter_despatches[0].cost_threshold == LetterCostThreshold.unsorted
    assert letter_despatches[1].notification_id == notification_bar.id
    assert letter_despatches[1].despatched_on == date(2023, 2, 22)
    assert letter_despatches[1].cost_threshold == LetterCostThreshold.sorted


def test_update_letter_notifications_statuses_builds_updates_list(notify_api):
    valid_file = "ref-foo|Sent|1|Unsorted|2023-02-23\nref-bar|Sent|2|Sorted|2023-02-22"
    updates = process_updates_from_file(valid_file, filename="file.txt")

    assert len(updates) == 2

    assert updates[0].reference == "ref-foo"
    assert updates[0].status == "Sent"
    assert updates[0].page_count == "1"
    assert updates[0].cost_threshold == LetterCostThreshold.unsorted
    assert updates[0].despatch_date == "2023-02-23"

    assert updates[1].reference == "ref-bar"
    assert updates[1].status == "Sent"
    assert updates[1].page_count == "2"
    assert updates[1].cost_threshold == LetterCostThreshold.sorted
    assert updates[1].despatch_date == "2023-02-22"


def test_update_letter_notifications_statuses_persisted(notify_api, mocker, sample_letter_template):
    sent_letter = create_notification(
        sample_letter_template, reference="ref-foo", status=NOTIFICATION_SENDING, billable_units=1
    )
    failed_letter = create_notification(
        sample_letter_template, reference="ref-bar", status=NOTIFICATION_SENDING, billable_units=2
    )
    create_service_callback_api(service=sample_letter_template.service, url="https://original_url.com")
    valid_file = (
        f"{sent_letter.reference}|Sent|1|Unsorted|2023-02-23\n{failed_letter.reference}|Failed|2|Sorted|2023-02-23"
    )
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)
    with pytest.raises(expected_exception=DVLAException) as e:
        update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")

    assert sent_letter.status == NOTIFICATION_DELIVERED
    assert sent_letter.billable_units == 1
    assert sent_letter.updated_at
    assert failed_letter.status == NOTIFICATION_TEMPORARY_FAILURE
    assert failed_letter.billable_units == 2
    assert failed_letter.updated_at
    assert "DVLA response file: {filename} has failed letters with notification.reference {failures}".format(
        filename="NOTIFY-20170823160812-RSP.TXT", failures=[format(failed_letter.reference)]
    ) in str(e.value)


def test_update_letter_notifications_does_not_call_send_callback_if_no_db_entry(
    notify_api, mocker, sample_letter_template, mock_celery_task
):
    sent_letter = create_notification(
        sample_letter_template, reference="ref-foo", status=NOTIFICATION_SENDING, billable_units=0
    )
    valid_file = f"{sent_letter.reference}|Sent|1|Unsorted|2022-08-11\n"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)

    send_mock = mock_celery_task(send_delivery_status_to_service)

    update_letter_notifications_statuses(filename="NOTIFY-20170823160812-RSP.TXT")
    send_mock.assert_not_called()


def test_check_billable_units_when_billable_units_matches_page_count(
    client, sample_letter_template, caplog, notification_update
):
    with caplog.at_level("ERROR"):
        create_notification(sample_letter_template, reference="REFERENCE_ABC", billable_units=1)

        check_billable_units(notification_update)

    assert caplog.messages == []


def test_check_billable_units_when_billable_units_does_not_match_page_count(
    client, sample_letter_template, caplog, notification_update
):
    with caplog.at_level("ERROR"):
        notification = create_notification(sample_letter_template, reference="REFERENCE_ABC", billable_units=3)

        check_billable_units(notification_update)

    assert (
        f"Notification with id {notification.id} has 3 billable_units but DVLA says page count is 1" in caplog.messages
    )


@pytest.mark.parametrize(
    "filename_date, billing_date", [("20170820230000", date(2017, 8, 21)), ("20170120230000", date(2017, 1, 20))]
)
def test_get_billing_date_in_bst_from_filename(filename_date, billing_date):
    filename = f"NOTIFY-{filename_date}-RSP.TXT"
    result = get_billing_date_in_bst_from_filename(filename)

    assert result == billing_date


@freeze_time("2018-01-11 09:00:00")
def test_persist_daily_sorted_letter_counts_saves_sorted_and_unsorted_values(client, notify_db_session):
    letter_counts = defaultdict(int, unsorted=5, sorted=1)
    persist_daily_sorted_letter_counts(date.today(), "test.txt", letter_counts)
    day = dao_get_daily_sorted_letter_by_billing_day(date.today())

    assert day.unsorted_count == 5
    assert day.sorted_count == 1


def test_record_daily_sorted_counts_persists_daily_sorted_letter_count(
    notify_api,
    notify_db_session,
    mocker,
):
    valid_file = (
        "Letter1|Sent|1|uNsOrTeD|2023-01-12\nLetter2|Sent|2|SORTED|2023-01-11\nLetter3|Sent|2|Sorted|2023-01-10"
    )
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)

    assert DailySortedLetter.query.count() == 0

    record_daily_sorted_counts(filename="NOTIFY-20170823160812-RSP.TXT")

    daily_sorted_counts = DailySortedLetter.query.all()
    assert len(daily_sorted_counts) == 1
    assert daily_sorted_counts[0].sorted_count == 2
    assert daily_sorted_counts[0].unsorted_count == 1


def test_record_daily_sorted_counts_raises_dvla_exception_with_unknown_sorted_status(
    notify_api,
    mocker,
):
    file_contents = "ref-foo|Failed|1|invalid|2023-01-01\nrow_2|Failed|1|MM|2023-01-01"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=file_contents)
    filename = "failed.txt"
    with pytest.raises(DVLAException) as e:
        record_daily_sorted_counts(filename=filename)

    assert f"DVLA response file: {filename} contains unknown Sorted status" in e.value.message
    assert "'mm'" in e.value.message
    assert "'invalid'" in e.value.message


def test_record_daily_sorted_counts_persists_daily_sorted_letter_count_with_no_sorted_values(
    notify_api, mocker, notify_db_session
):
    valid_file = "Letter1|Sent|1|Unsorted|2023-01-01\nLetter2|Sent|2|Unsorted|2023-01-01"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)

    record_daily_sorted_counts(filename="NOTIFY-20170823160812-RSP.TXT")

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 2
    assert daily_sorted_letter.sorted_count == 0


def test_record_daily_sorted_counts_can_run_twice_for_same_file(notify_api, mocker, notify_db_session):
    valid_file = "Letter1|Sent|1|sorted|2023-01-01\nLetter2|Sent|2|Unsorted|2023-01-01"
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=valid_file)

    record_daily_sorted_counts(filename="NOTIFY-20170823160812-RSP.TXT")

    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 1
    assert daily_sorted_letter.sorted_count == 1

    updated_file = (
        "Letter1|Sent|1|sorted|2023-01-01\nLetter2|Sent|2|Unsorted|2023-01-01\nLetter3|Sent|2|Unsorted|2023-01-01"
    )
    mocker.patch("app.celery.tasks.s3.get_s3_file", return_value=updated_file)

    record_daily_sorted_counts(filename="NOTIFY-20170823160812-RSP.TXT")
    daily_sorted_letter = dao_get_daily_sorted_letter_by_billing_day(date(2017, 8, 23))

    assert daily_sorted_letter.unsorted_count == 2
    assert daily_sorted_letter.sorted_count == 1
