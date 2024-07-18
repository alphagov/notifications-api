from app.constants import EMAIL_TYPE
from app.dao.unsubscribe_request_dao import (
    create_unsubscribe_request_dao,
    create_unsubscribe_request_reports_dao,
    get_unsubscribe_request_by_notification_id_dao,
    get_unsubscribe_requests_statistics_dao,
)
from app.models import UnsubscribeRequest, UnsubscribeRequestReport
from app.one_click_unsubscribe.rest import get_unsubscribe_request_data
from tests.app.db import create_notification, create_template


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
    """
    This test creates 2 un-batched unprocessed unsubscribe requests, 1 batched  unprocessed unsubscribe request
    and 1 batched processed unsubscribe requests.

     The test cases covered are
     i.The batched unprocessed unsubscribe request is included in the count_of_pending_unsubscribe_requests
     ii.The right datetime_of_latest_unsubscribe_request is returned.
    """
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
            "created_at": "2024-07-12 13:30:00",
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
            "created_at": "2024-07-10 21:19:56",
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
            "created_at": "2024-07-08 17:20:50",
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
            "created_at": "2024-07-04 11:55:23",
        }
    )

    # Create 2 unsubscribe_request_reports, one processed and the other not processed
    unsubscribe_request_report_1 = UnsubscribeRequestReport(
        id="7536fd15-3d9c-494b-9053-0fd9822bcae6",
        count=141,
        earliest_timestamp="2024-07-02 21:35:36",
        latest_timestamp="2024-07-05 11:55:23",
        processed_by_service_at="2024-07-10 15:16:23",
        service_id=sample_service.id,
    )
    create_unsubscribe_request_reports_dao(unsubscribe_request_report_1)

    unsubscribe_request_report_2 = UnsubscribeRequestReport(
        id="1e37cd8c-bbe0-4ed9-b1f5-273d371ffd0e",
        count=242,
        earliest_timestamp="2024-07-05 11:55:23",
        latest_timestamp="2024-07-09 13:22:44",
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
        "unprocessed_unsubscribe_requests_count": 3,
        "datetime_of_latest_unsubscribe_request": unsubscribe_requests[0].created_at,
    }

    assert result["count_of_pending_unsubscribe_requests"] == expected_result["unprocessed_unsubscribe_requests_count"]
    assert result["datetime_of_latest_unsubscribe_request"] == expected_result["datetime_of_latest_unsubscribe_request"]
