from datetime import datetime

from freezegun import freeze_time

from app.constants import EMAIL_TYPE
from app.dao.unsubscribe_request_dao import (
    assign_unbatched_unsubscribe_requests_to_report_dao,
    create_unsubscribe_request_dao,
    get_latest_unsubscribe_request_date_dao,
    get_unsubscribe_request_by_notification_id_dao,
    get_unsubscribe_request_report_by_id_dao,
    get_unsubscribe_request_reports_dao,
    get_unsubscribe_requests_data_for_download_dao,
    get_unsubscribe_requests_statistics_dao,
)
from app.models import UnsubscribeRequest
from app.one_click_unsubscribe.rest import get_unsubscribe_request_data
from app.utils import midnight_n_days_ago
from tests.app.db import (
    create_job,
    create_service,
    create_template,
    create_unsubscribe_request,
    create_unsubscribe_request_report,
)


def test_create_unsubscribe_request_dao(sample_email_notification):
    email_address = "foo@bar"
    unsubscribe_data = get_unsubscribe_request_data(sample_email_notification, email_address)
    create_unsubscribe_request_dao(unsubscribe_data)
    unsubscribe_request = get_unsubscribe_request_by_notification_id_dao(sample_email_notification.id)
    assert unsubscribe_request.notification_id == sample_email_notification.id
    assert unsubscribe_request.email_address == email_address
    assert unsubscribe_request.template_id == sample_email_notification.template_id
    assert unsubscribe_request.template_version == sample_email_notification.template_version
    assert unsubscribe_request.service_id == sample_email_notification.service_id


def test_get_unsubscribe_requests_statistics_dao(sample_service):

    # Create 2 un-batched unsubscribe requests
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(1))
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(2))

    # Create 2 batched unsubscribe requests
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(4))
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(6))

    # This request should not be counted because it’s more than 7 days ago
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(8))

    # This request should not be counted because it’s from a different service
    create_unsubscribe_request(create_service(service_name="Other service"), created_at=midnight_n_days_ago(4))

    # Create 2 unsubscribe_request_reports, one processed and the other not processed
    unsubscribe_request_report_1 = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(6),
        latest_timestamp=midnight_n_days_ago(5),
        processed_by_service_at=midnight_n_days_ago(3),
    )

    unsubscribe_request_report_2 = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(5),
        latest_timestamp=midnight_n_days_ago(4),
    )

    # Retrieve the created unsubscribe requests and batch the two earliest requests, with the earliest report
    # being processed.
    unsubscribe_requests = UnsubscribeRequest.query.order_by(UnsubscribeRequest.created_at.desc()).all()
    unsubscribe_requests[2].unsubscribe_request_report_id = unsubscribe_request_report_1.id
    unsubscribe_requests[3].unsubscribe_request_report_id = unsubscribe_request_report_2.id

    result = get_unsubscribe_requests_statistics_dao(sample_service.id)
    expected_result = {
        "unsubscribe_requests_count": 4,
        "datetime_of_latest_unsubscribe_request": unsubscribe_requests[0].created_at,
    }

    assert result.unsubscribe_requests_count == expected_result["unsubscribe_requests_count"]
    assert result.datetime_of_latest_unsubscribe_request == expected_result["datetime_of_latest_unsubscribe_request"]


def test_get_unsubscribe_requests_statistics_dao_returns_none_when_there_are_no_unsubscribe_requests(
    sample_service,
):
    result = get_unsubscribe_requests_statistics_dao(sample_service.id)
    assert result is None


def test_get_unsubscribe_requests_statistics_dao_adheres_to_7_days_limit(sample_service):
    # Create 2 un-batched unsubscribe requests, with 1 request created outside the 7 days limit
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(7))
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(8))

    unsubscribe_requests = UnsubscribeRequest.query.order_by(UnsubscribeRequest.created_at.desc()).all()
    result = get_unsubscribe_requests_statistics_dao(sample_service.id)
    expected_result = {
        "unsubscribe_requests_count": 1,
        "datetime_of_latest_unsubscribe_request": unsubscribe_requests[0].created_at,
    }

    assert result.unsubscribe_requests_count == expected_result["unsubscribe_requests_count"]
    assert result.datetime_of_latest_unsubscribe_request == expected_result["datetime_of_latest_unsubscribe_request"]


def test_get_latest_unsubscribe_request_dao(sample_service):
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(3))
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(5))

    unsubscribe_requests = UnsubscribeRequest.query.order_by(UnsubscribeRequest.created_at.desc()).all()
    result = get_latest_unsubscribe_request_date_dao(sample_service.id)
    assert result.datetime_of_latest_unsubscribe_request == unsubscribe_requests[0].created_at


def test_get_latest_unsubscribe_request_dao_if_no_unsubscribe_request_exists(sample_service):
    result = get_latest_unsubscribe_request_date_dao(sample_service.id)
    assert result is None


def test_assign_unbatched_unsubscribe_requests_to_report_dao(sample_service):
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(0))
    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(2))

    unsubscribe_request_report = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
    )

    assign_unbatched_unsubscribe_requests_to_report_dao(
        report_id=unsubscribe_request_report.id,
        service_id=unsubscribe_request_report.service_id,
        earliest_timestamp=unsubscribe_request_report.earliest_timestamp,
        latest_timestamp=unsubscribe_request_report.latest_timestamp,
    )
    unsubscribe_requests = UnsubscribeRequest.query.filter_by(
        unsubscribe_request_report_id=unsubscribe_request_report.id
    ).all()

    for unsubscribe_request in unsubscribe_requests:
        assert unsubscribe_request.unsubscribe_request_report_id == unsubscribe_request_report.id
    assert len(unsubscribe_requests) == 2


def test_unsubscribe_reports_only_includes_those_with_requests(sample_service):
    unsubscribe_request_report_1 = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
    )

    create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
    )

    create_unsubscribe_request(sample_service, created_at=midnight_n_days_ago(3))

    assign_unbatched_unsubscribe_requests_to_report_dao(
        report_id=unsubscribe_request_report_1.id,
        service_id=unsubscribe_request_report_1.service_id,
        earliest_timestamp=unsubscribe_request_report_1.earliest_timestamp,
        latest_timestamp=unsubscribe_request_report_1.latest_timestamp,
    )
    assert list(get_unsubscribe_request_reports_dao(sample_service.id)) == [unsubscribe_request_report_1]


@freeze_time("2024-07-20 20:20")
def test_get_unsubscribe_request_data_for_download_dao(sample_service):
    unsubscribe_request_report = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
    )

    job_1 = create_job(
        template=create_template(sample_service, EMAIL_TYPE, template_name="first Template"),
        original_file_name="contact list",
    )
    job_2 = create_job(
        template=create_template(sample_service, EMAIL_TYPE, template_name="Another Template"),
        original_file_name="another contact list",
    )

    for email_address, created_at_days_ago, job in (
        ("foo@bar.com", 1, job_1),
        ("fizz@bar.com", 2, job_1),
        ("buzz@bar.com", 3, job_2),
        ("fizzbuzz@bar.com", 4, None),
    ):
        create_unsubscribe_request(
            sample_service,
            email_address=email_address,
            created_at=midnight_n_days_ago(created_at_days_ago),
            job=job,
            unsubscribe_request_report_id=unsubscribe_request_report.id,
        )

    result = get_unsubscribe_requests_data_for_download_dao(sample_service.id, unsubscribe_request_report.id)

    for row, expected in zip(
        result,
        [
            {
                "email_address": "foo@bar.com",
                "template_name": "first Template",
                "original_file_name": "contact list",
                "template_sent_at": datetime(2024, 7, 17, 23, 0),
                "unsubscribe_request_received_at": datetime(2024, 7, 18, 23, 0),
            },
            {
                "email_address": "fizz@bar.com",
                "template_name": "first Template",
                "original_file_name": "contact list",
                "template_sent_at": datetime(2024, 7, 16, 23, 0),
                "unsubscribe_request_received_at": datetime(2024, 7, 17, 23, 0),
            },
            {
                "email_address": "fizzbuzz@bar.com",
                "template_name": "email Template Name",
                "original_file_name": "N/A",
                "template_sent_at": datetime(2024, 7, 14, 23, 0),
                "unsubscribe_request_received_at": datetime(2024, 7, 15, 23, 0),
            },
            {
                "email_address": "buzz@bar.com",
                "template_name": "Another Template",
                "original_file_name": "another contact list",
                "template_sent_at": datetime(2024, 7, 15, 23, 0),
                "unsubscribe_request_received_at": datetime(2024, 7, 16, 23, 0),
            },
        ],
        strict=True,
    ):
        assert row.email_address == expected["email_address"]
        assert row.template_name == expected["template_name"]
        assert row.original_file_name == expected["original_file_name"]
        assert row.template_sent_at == expected["template_sent_at"]
        assert row.unsubscribe_request_received_at == expected["unsubscribe_request_received_at"]


def test_get_unsubscribe_request_data_for_download_dao_invalid_batch_id(sample_service):
    result = get_unsubscribe_requests_data_for_download_dao(sample_service.id, "c5019907-656a-4adf-9c02-da422529e507")
    assert result == []


def test_get_unsubscribe_request_report_by_id_dao(sample_service):
    unsubscribe_request_report = create_unsubscribe_request_report(
        sample_service,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
    )

    result = get_unsubscribe_request_report_by_id_dao(unsubscribe_request_report.id)
    assert result.id == unsubscribe_request_report.id
    assert result.count == unsubscribe_request_report.count
    assert result.earliest_timestamp == unsubscribe_request_report.earliest_timestamp
    assert result.latest_timestamp == unsubscribe_request_report.latest_timestamp
    assert result.service_id == unsubscribe_request_report.service_id


def test_get_unsubscribe_request_report_by_id_dao_invalid_service_id(sample_service):
    result = get_unsubscribe_request_report_by_id_dao("c5019907-656a-4adf-9c02-da422529e507")
    assert result is None
