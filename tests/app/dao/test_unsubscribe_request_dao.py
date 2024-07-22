from app.constants import EMAIL_TYPE
from app.dao.unsubscribe_request_dao import (
    create_unsubscribe_request_dao,
    create_unsubscribe_request_reports_dao,
    get_latest_unsubscribe_request_date_dao,
    get_unsubscribe_request_by_notification_id_dao,
    get_unsubscribe_requests_statistics_dao,
)
from app.models import UnsubscribeRequest, UnsubscribeRequestReport
from app.one_click_unsubscribe.rest import get_unsubscribe_request_data
from app.utils import midnight_n_days_ago
from tests.app.db import create_notification, create_service, create_template


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
