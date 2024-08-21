from sqlalchemy import desc

from app.constants import EMAIL_TYPE
from app.dao.unsubscribe_request_dao import (
    assign_unbatched_unsubscribe_requests_to_report_dao,
    create_unsubscribe_request_dao,
    create_unsubscribe_request_reports_dao,
    get_latest_unsubscribe_request_date_dao,
    get_unsubscribe_request_by_notification_id_dao,
    get_unsubscribe_request_report_by_id_dao,
    get_unsubscribe_requests_data_for_download_dao,
    get_unsubscribe_requests_statistics_dao,
)
from app.models import UnsubscribeRequest, UnsubscribeRequestReport
from app.one_click_unsubscribe.rest import get_unsubscribe_request_data
from app.utils import midnight_n_days_ago
from tests.app.db import create_job, create_notification, create_service, create_template


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
    template_1 = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    notification_1 = create_notification(template=template_1)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_1.id,
            "template_id": notification_1.template_id,
            "template_version": notification_1.template_version,
            "service_id": notification_1.service_id,
            "email_address": notification_1.to,
            "created_at": midnight_n_days_ago(1),
        }
    )

    notification_2 = create_notification(template=template_1)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_2.id,
            "template_id": notification_2.template_id,
            "template_version": notification_2.template_version,
            "service_id": notification_2.service_id,
            "email_address": notification_2.to,
            "created_at": midnight_n_days_ago(2),
        }
    )

    # Create 2 batched unsubscribe requests
    template_2 = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    notification_3 = create_notification(template=template_2)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_3.id,
            "template_id": notification_3.template_id,
            "template_version": notification_3.template_version,
            "service_id": notification_3.service_id,
            "email_address": notification_3.to,
            "created_at": midnight_n_days_ago(4),
        }
    )

    notification_4 = create_notification(template=template_2)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_4.id,
            "template_id": notification_4.template_id,
            "template_version": notification_4.template_version,
            "service_id": notification_4.service_id,
            "email_address": notification_4.to,
            "created_at": midnight_n_days_ago(6),
        }
    )

    notification_5 = create_notification(template=template_2)
    # This request should not be counted because it’s more than 7 days ago
    create_unsubscribe_request_dao(
        {
            "notification_id": notification_5.id,
            "template_id": notification_5.template_id,
            "template_version": notification_5.template_version,
            "service_id": notification_5.service_id,
            "email_address": notification_5.to,
            "created_at": midnight_n_days_ago(8),
        }
    )

    other_service_template = create_template(
        create_service(service_name="Other service"),
        template_type=EMAIL_TYPE,
    )
    notification_6 = create_notification(template=other_service_template)
    # This request should not be counted because it’s from a different service
    create_unsubscribe_request_dao(
        {
            "notification_id": notification_6.id,
            "template_id": notification_6.template_id,
            "template_version": notification_6.template_version,
            "service_id": notification_6.service_id,
            "email_address": notification_6.to,
            "created_at": midnight_n_days_ago(1),
        }
    )

    # Create 2 unsubscribe_request_reports, one processed and the other not processed
    unsubscribe_request_report_1 = UnsubscribeRequestReport(
        id="7536fd15-3d9c-494b-9053-0fd9822bcae6",
        count=141,
        earliest_timestamp=midnight_n_days_ago(6),
        latest_timestamp=midnight_n_days_ago(5),
        processed_by_service_at=midnight_n_days_ago(3),
        service_id=sample_service.id,
    )
    create_unsubscribe_request_reports_dao(unsubscribe_request_report_1)

    unsubscribe_request_report_2 = UnsubscribeRequestReport(
        id="1e37cd8c-bbe0-4ed9-b1f5-273d371ffd0e",
        count=242,
        earliest_timestamp=midnight_n_days_ago(5),
        latest_timestamp=midnight_n_days_ago(4),
        processed_by_service_at=None,
        service_id=sample_service.id,
    )
    create_unsubscribe_request_reports_dao(unsubscribe_request_report_2)

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
    template_1 = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    notification_1 = create_notification(template=template_1)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_1.id,
            "template_id": notification_1.template_id,
            "template_version": notification_1.template_version,
            "service_id": notification_1.service_id,
            "email_address": notification_1.to,
            "created_at": midnight_n_days_ago(7),
        }
    )

    notification_2 = create_notification(template=template_1)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_2.id,
            "template_id": notification_2.template_id,
            "template_version": notification_2.template_version,
            "service_id": notification_2.service_id,
            "email_address": notification_2.to,
            "created_at": midnight_n_days_ago(8),
        }
    )
    unsubscribe_requests = UnsubscribeRequest.query.order_by(UnsubscribeRequest.created_at.desc()).all()
    result = get_unsubscribe_requests_statistics_dao(sample_service.id)
    expected_result = {
        "unsubscribe_requests_count": 1,
        "datetime_of_latest_unsubscribe_request": unsubscribe_requests[0].created_at,
    }

    assert result.unsubscribe_requests_count == expected_result["unsubscribe_requests_count"]
    assert result.datetime_of_latest_unsubscribe_request == expected_result["datetime_of_latest_unsubscribe_request"]


def test_get_latest_unsubscribe_request_dao(sample_service):
    template = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    notification_1 = create_notification(template=template)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_1.id,
            "template_id": notification_1.template_id,
            "template_version": notification_1.template_version,
            "service_id": notification_1.service_id,
            "email_address": notification_1.to,
            "created_at": midnight_n_days_ago(3),
        }
    )

    notification_2 = create_notification(template=template)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_2.id,
            "template_id": notification_2.template_id,
            "template_version": notification_2.template_version,
            "service_id": notification_2.service_id,
            "email_address": notification_2.to,
            "created_at": midnight_n_days_ago(5),
        }
    )
    unsubscribe_requests = UnsubscribeRequest.query.order_by(UnsubscribeRequest.created_at.desc()).all()
    result = get_latest_unsubscribe_request_date_dao(sample_service.id)
    assert result.datetime_of_latest_unsubscribe_request == unsubscribe_requests[0].created_at


def test_get_latest_unsubscribe_request_dao_if_no_unsubscribe_request_exists(sample_service):
    result = get_latest_unsubscribe_request_date_dao(sample_service.id)
    assert result is None


def test_assign_unbatched_unsubscribe_requests_to_report_dao(sample_service):
    template = create_template(
        sample_service,
        template_type=EMAIL_TYPE,
    )
    notification_1 = create_notification(template=template)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_1.id,
            "template_id": notification_1.template_id,
            "template_version": notification_1.template_version,
            "service_id": notification_1.service_id,
            "email_address": notification_1.to,
            "created_at": midnight_n_days_ago(0),
        }
    )
    notification_2 = create_notification(template=template)
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_2.id,
            "template_id": notification_2.template_id,
            "template_version": notification_2.template_version,
            "service_id": notification_2.service_id,
            "email_address": notification_2.to,
            "created_at": midnight_n_days_ago(2),
        }
    )

    unsubscribe_request_report = UnsubscribeRequestReport(
        id="7536fd15-3d9c-494b-9053-0fd9822bcae6",
        count=141,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
        service_id=sample_service.id,
    )
    create_unsubscribe_request_reports_dao(unsubscribe_request_report)

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


def test_get_unsubscribe_request_data_for_download_dao(sample_service):
    unsubscribe_request_report = UnsubscribeRequestReport(
        id="7536fd15-3d9c-494b-9053-0fd9822bcae6",
        count=141,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
        service_id=sample_service.id,
    )
    create_unsubscribe_request_reports_dao(unsubscribe_request_report)
    template_1 = create_template(
        sample_service,
        template_name="first Template",
        template_type=EMAIL_TYPE,
    )
    job_1 = create_job(template=template_1, original_file_name="contact list")
    notification_1 = create_notification(
        template=template_1, job=job_1, to_field="foo@bar.com", sent_at=midnight_n_days_ago(1)
    )
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_1.id,
            "template_id": notification_1.template_id,
            "template_version": notification_1.template_version,
            "service_id": notification_1.service_id,
            "email_address": notification_1.to,
            "created_at": midnight_n_days_ago(1),
            "unsubscribe_request_report_id": unsubscribe_request_report.id,
        }
    )
    notification_2 = create_notification(
        template=template_1, job=job_1, to_field="fizz@bar.com", sent_at=midnight_n_days_ago(2)
    )
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_2.id,
            "template_id": notification_2.template_id,
            "template_version": notification_2.template_version,
            "service_id": notification_2.service_id,
            "email_address": notification_2.to,
            "created_at": midnight_n_days_ago(2),
            "unsubscribe_request_report_id": unsubscribe_request_report.id,
        }
    )
    template_2 = create_template(
        service=sample_service,
        template_name="Another Template",
        template_type=EMAIL_TYPE,
    )
    job_2 = create_job(template=template_2, original_file_name="another contact list")
    notification_3 = create_notification(
        template=template_2, job=job_2, to_field="buzz@bar.com", sent_at=midnight_n_days_ago(3)
    )
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_3.id,
            "template_id": notification_3.template_id,
            "template_version": notification_3.template_version,
            "service_id": notification_3.service_id,
            "email_address": notification_3.to,
            "created_at": midnight_n_days_ago(3),
            "unsubscribe_request_report_id": unsubscribe_request_report.id,
        }
    )
    notification_4 = create_notification(
        template=template_2, to_field="fizzbuzz@bar.com", sent_at=midnight_n_days_ago(4)
    )
    create_unsubscribe_request_dao(
        {  # noqa
            "notification_id": notification_4.id,
            "template_id": notification_4.template_id,
            "template_version": notification_4.template_version,
            "service_id": notification_4.service_id,
            "email_address": notification_4.to,
            "created_at": midnight_n_days_ago(4),
            "unsubscribe_request_report_id": unsubscribe_request_report.id,
        }
    )

    result = get_unsubscribe_requests_data_for_download_dao(sample_service.id, unsubscribe_request_report.id)
    created_unsubscribe_requests = UnsubscribeRequest.query.order_by(desc(UnsubscribeRequest.created_at)).all()

    assert result[0].email_address == notification_1.to
    assert result[0].template_name == notification_1.template.name
    assert result[0].original_file_name == notification_1.job.original_file_name
    assert result[0].template_sent_at == notification_1.sent_at
    assert result[0].unsubscribe_request_received_at == created_unsubscribe_requests[0].created_at
    assert result[1].email_address == notification_2.to
    assert result[1].template_name == notification_2.template.name
    assert result[1].original_file_name == notification_2.job.original_file_name
    assert result[1].template_sent_at == notification_2.sent_at
    assert result[1].unsubscribe_request_received_at == created_unsubscribe_requests[1].created_at
    assert result[2].email_address == notification_4.to
    assert result[2].template_name == notification_4.template.name
    assert result[2].original_file_name == "N/A"
    assert result[2].template_sent_at == notification_4.sent_at
    assert result[2].unsubscribe_request_received_at == created_unsubscribe_requests[3].created_at
    assert result[3].email_address == notification_3.to
    assert result[3].template_name == notification_3.template.name
    assert result[3].original_file_name == notification_3.job.original_file_name
    assert result[3].template_sent_at == notification_3.sent_at
    assert result[3].unsubscribe_request_received_at == created_unsubscribe_requests[2].created_at


def test_get_unsubscribe_request_data_for_download_dao_invalid_batch_id(sample_service):
    result = get_unsubscribe_requests_data_for_download_dao(sample_service.id, "c5019907-656a-4adf-9c02-da422529e507")
    assert result == []


def test_get_unsubscribe_request_report_by_id_dao(sample_service):
    unsubscribe_request_report = UnsubscribeRequestReport(
        id="7536fd15-3d9c-494b-9053-0fd9822bcae6",
        count=141,
        earliest_timestamp=midnight_n_days_ago(4),
        latest_timestamp=midnight_n_days_ago(0),
        service_id=sample_service.id,
    )
    create_unsubscribe_request_reports_dao(unsubscribe_request_report)
    result = get_unsubscribe_request_report_by_id_dao(unsubscribe_request_report.id)
    assert result.id == unsubscribe_request_report.id
    assert result.count == unsubscribe_request_report.count
    assert result.earliest_timestamp == unsubscribe_request_report.earliest_timestamp
    assert result.latest_timestamp == unsubscribe_request_report.latest_timestamp
    assert result.service_id == unsubscribe_request_report.service_id


def test_get_unsubscribe_request_report_by_id_dao_invalid_service_id(sample_service):
    result = get_unsubscribe_request_report_by_id_dao("c5019907-656a-4adf-9c02-da422529e507")
    assert result is None
