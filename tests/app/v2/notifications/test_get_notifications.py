import datetime

import pytest
from flask import url_for

from app.utils import DATETIME_FORMAT
from tests import create_service_authorization_header
from tests.app.db import create_letter_rate, create_notification, create_template


@pytest.mark.parametrize("billable_units, provider", [(1, "mmg"), (0, "mmg"), (1, None)])
def test_get_notification_by_id_returns_200(api_client_request, sample_template, sms_rate, billable_units, provider):
    sample_notification = create_notification(
        template=sample_template,
        billable_units=billable_units,
        sent_by=provider,
    )

    # another
    create_notification(
        template=sample_template,
        billable_units=billable_units,
        sent_by=provider,
    )

    json_response = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_notification_by_id",
        notification_id=sample_notification.id,
    )

    expected_template_response = {
        "id": "{}".format(sample_notification.serialize()["template"]["id"]),
        "version": sample_notification.serialize()["template"]["version"],
        "uri": sample_notification.serialize()["template"]["uri"],
    }

    expected_response = {
        "id": f"{sample_notification.id}",
        "reference": None,
        "email_address": None,
        "phone_number": f"{sample_notification.to}",
        "line_1": None,
        "line_2": None,
        "line_3": None,
        "line_4": None,
        "line_5": None,
        "line_6": None,
        "postcode": None,
        "type": f"{sample_notification.notification_type}",
        "status": f"{sample_notification.status}",
        "template": expected_template_response,
        "created_at": sample_notification.created_at.strftime(DATETIME_FORMAT),
        "created_by_name": None,
        "body": sample_notification.template.content,
        "subject": None,
        "sent_at": sample_notification.sent_at,
        "completed_at": sample_notification.completed_at(),
        "scheduled_for": None,
        "postage": None,
        "one_click_unsubscribe_url": None,
        "is_cost_data_ready": True if billable_units else False,
        "cost_in_pounds": 0.0227 * billable_units if billable_units else None,
        "cost_details": (
            {"billable_sms_fragments": billable_units, "international_rate_multiplier": 1, "sms_rate": 0.0227}
            if billable_units
            else {}
        ),
    }

    assert json_response == expected_response


def test_get_notification_by_id_with_placeholders_returns_200(
    api_client_request, sample_email_template_with_placeholders, sms_rate
):
    sample_notification = create_notification(
        template=sample_email_template_with_placeholders, personalisation={"name": "Bob"}
    )

    json_response = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_notification_by_id",
        notification_id=sample_notification.id,
    )

    expected_template_response = {
        "id": "{}".format(sample_notification.serialize()["template"]["id"]),
        "version": sample_notification.serialize()["template"]["version"],
        "uri": sample_notification.serialize()["template"]["uri"],
    }

    expected_response = {
        "id": f"{sample_notification.id}",
        "reference": None,
        "email_address": f"{sample_notification.to}",
        "phone_number": None,
        "line_1": None,
        "line_2": None,
        "line_3": None,
        "line_4": None,
        "line_5": None,
        "line_6": None,
        "postcode": None,
        "type": f"{sample_notification.notification_type}",
        "status": f"{sample_notification.status}",
        "template": expected_template_response,
        "created_at": sample_notification.created_at.strftime(DATETIME_FORMAT),
        "created_by_name": None,
        "body": "Hello Bob\nThis is an email from GOV.UK",
        "subject": "Bob",
        "sent_at": sample_notification.sent_at,
        "completed_at": sample_notification.completed_at(),
        "scheduled_for": None,
        "postage": None,
        "one_click_unsubscribe_url": None,
        "is_cost_data_ready": True,
        "cost_in_pounds": 0.00,
        "cost_details": {},
    }

    assert json_response == expected_response


def test_get_notification_by_reference_returns_200(api_client_request, sample_template, sms_rate):
    sample_notification_with_reference = create_notification(
        template=sample_template, client_reference="some-client-reference"
    )

    json_response = api_client_request.get(
        sample_notification_with_reference.service_id,
        "v2_notifications.get_notifications",
        reference=sample_notification_with_reference.client_reference,
    )

    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(sample_notification_with_reference.id)
    assert json_response["notifications"][0]["reference"] == "some-client-reference"


def test_get_notification_by_id_returns_created_by_name_if_notification_created_by_id(
    api_client_request,
    sample_user,
    sample_template,
    sms_rate,
):
    sms_notification = create_notification(template=sample_template)
    sms_notification.created_by_id = sample_user.id

    json_response = api_client_request.get(
        sms_notification.service_id, "v2_notifications.get_notification_by_id", notification_id=sms_notification.id
    )

    assert json_response["created_by_name"] == "Test User"


def test_get_notification_by_reference_nonexistent_reference_returns_no_notifications(
    api_client_request, sample_service
):
    json_response = api_client_request.get(
        sample_service.id, "v2_notifications.get_notifications", reference="nonexistent-reference"
    )

    assert len(json_response["notifications"]) == 0


def test_get_notification_by_id_nonexistent_id(api_client_request, sample_notification):
    json_response = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_notification_by_id",
        notification_id="dd4b8b9d-d414-4a83-9256-580046bf18f9",
        _expected_status=404,
    )

    assert json_response == {"errors": [{"error": "NoResultFound", "message": "No result found"}], "status_code": 404}


@pytest.mark.parametrize("id", ["1234-badly-formatted-id-7890", "0"])
def test_get_notification_by_id_invalid_id(api_client_request, sample_notification, id):
    json_response = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_notification_by_id",
        notification_id=id,
        _expected_status=400,
    )

    assert json_response == {
        "errors": [{"error": "ValidationError", "message": "notification_id is not a valid UUID"}],
        "status_code": 400,
    }


@pytest.mark.parametrize(
    "created_at_month, postage, estimated_delivery",
    [
        # no print during weekends, no delivery on Sundays
        (12, "second", "2000-12-11T16:00:00.000000Z"),  # Created Fri 1 Dec, printed Mon 4 Dec, delivered Mon 11 Dec
        (6, "second", "2000-06-09T15:00:00.000000Z"),  # Created Thu 1 Jun, printed Fri 2 Jun, delivered Fri 9 Jun
        (12, "first", "2000-12-05T16:00:00.000000Z"),  # Created Fri 1 Dec, printed Mon 4 Dec, delivered Tue 5 Dec
        (6, "first", "2000-06-03T15:00:00.000000Z"),  # Created Thu 1 Jun, printed Fri 2 Jun, delivered Sat 3 Jun
        (12, "economy", "2000-12-13T16:00:00.000000Z"),  # Created Fri 1 Dec, printed Mon 4 Dec, delivered Weds 13 Dec
        (6, "economy", "2000-06-13T15:00:00.000000Z"),  # Created Thu 1 Jun, printed Fri 2 Jun, delivery Fri 13 Jun
    ],
)
def test_get_notification_adds_delivery_estimate_for_letters(
    api_client_request,
    sample_letter_notification,
    created_at_month,
    postage,
    estimated_delivery,
):
    create_letter_rate(start_date=datetime.datetime(2000, 1, 1), rate=0.82, post_class="first", sheet_count=1)
    create_letter_rate(start_date=datetime.datetime(2000, 1, 1), rate=0.82, post_class="second", sheet_count=1)
    create_letter_rate(start_date=datetime.datetime(2000, 1, 1), rate=0.82, post_class="economy", sheet_count=1)
    sample_letter_notification.created_at = datetime.datetime(2000, created_at_month, 1)
    sample_letter_notification.postage = postage

    json_response = api_client_request.get(
        sample_letter_notification.service_id,
        "v2_notifications.get_notification_by_id",
        notification_id=sample_letter_notification.id,
    )

    assert json_response["postage"] == postage
    assert json_response["estimated_delivery"] == estimated_delivery


@pytest.mark.parametrize("template_type", ["sms", "email"])
def test_get_notification_doesnt_have_delivery_estimate_for_non_letters(
    api_client_request,
    sample_service,
    sms_rate,
    template_type,
):
    template = create_template(service=sample_service, template_type=template_type)
    mocked_notification = create_notification(template=template)

    json_response = api_client_request.get(
        mocked_notification.service_id,
        "v2_notifications.get_notification_by_id",
        notification_id=mocked_notification.id,
    )

    assert "estimated_delivery" not in json_response


def test_get_all_notifications_except_job_notifications_returns_200(
    api_client_request, sample_template, sample_job, sms_rate
):
    create_notification(template=sample_template, job=sample_job)  # should not return this job notification
    notifications = [create_notification(template=sample_template) for _ in range(2)]
    notification = notifications[-1]

    json_response = api_client_request.get(sample_template.service_id, "v2_notifications.get_notifications")

    assert json_response["links"]["current"].endswith("/v2/notifications")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 2

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == "created"
    assert json_response["notifications"][0]["template"] == {
        "id": str(notification.template.id),
        "uri": notification.template.get_link(),
        "version": 1,
    }
    assert json_response["notifications"][0]["phone_number"] == "+447700900855"
    assert json_response["notifications"][0]["type"] == "sms"
    assert not json_response["notifications"][0]["scheduled_for"]


def test_get_all_notifications_with_include_jobs_arg_returns_200(
    api_client_request, sample_template, sample_job, sms_rate
):
    notifications = [
        create_notification(template=sample_template, job=sample_job),
        create_notification(template=sample_template),
    ]
    notification = notifications[-1]

    json_response = api_client_request.get(
        sample_template.service_id,
        "v2_notifications.get_notifications",
        include_jobs="true",
    )

    assert json_response["links"]["current"].endswith("/v2/notifications?include_jobs=true")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 2

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == notification.status
    assert json_response["notifications"][0]["phone_number"] == notification.to
    assert json_response["notifications"][0]["type"] == notification.template.template_type
    assert not json_response["notifications"][0]["scheduled_for"]


def test_get_all_notifications_no_notifications_if_no_notifications(api_client_request, sample_service):
    json_response = api_client_request.get(
        sample_service.id,
        "v2_notifications.get_notifications",
    )

    assert json_response["links"]["current"].endswith("/v2/notifications")
    assert "next" not in json_response["links"].keys()
    assert len(json_response["notifications"]) == 0


def test_get_all_notifications_filter_by_template_type(api_client_request, sample_service):
    email_template = create_template(service=sample_service, template_type="email")
    sms_template = create_template(service=sample_service, template_type="sms")

    notification = create_notification(template=email_template, to_field="don.draper@scdp.biz")
    create_notification(template=sms_template)

    json_response = api_client_request.get(
        notification.service_id,
        "v2_notifications.get_notifications",
        template_type="email",
    )

    assert json_response["links"]["current"].endswith("/v2/notifications?template_type=email")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == "created"
    assert json_response["notifications"][0]["template"] == {
        "id": str(email_template.id),
        "uri": notification.template.get_link(),
        "version": 1,
    }
    assert json_response["notifications"][0]["email_address"] == "don.draper@scdp.biz"
    assert json_response["notifications"][0]["type"] == "email"


def test_get_all_notifications_filter_by_template_type_invalid_template_type(api_client_request, sample_notification):
    json_response = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_notifications",
        template_type="orange",
        _expected_status=400,
    )

    assert json_response["status_code"] == 400
    assert len(json_response["errors"]) == 1
    assert json_response["errors"][0]["message"] == "template_type orange is not one of [sms, email, letter]"


def test_get_all_notifications_filter_by_single_status(api_client_request, sample_template, sms_rate):
    notification = create_notification(template=sample_template, status="pending")
    create_notification(template=sample_template)

    json_response = api_client_request.get(
        notification.service_id,
        "v2_notifications.get_notifications",
        status="pending",
    )

    assert json_response["links"]["current"].endswith("/v2/notifications?status=pending")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(notification.id)
    assert json_response["notifications"][0]["status"] == "pending"


@pytest.mark.parametrize(
    "internal_status, filter_status, expect_num_notifications",
    (
        ("created", "accepted", 1),
        ("sending", "accepted", 1),
        ("delivered", "received", 1),
        pytest.param(
            "returned-letter",
            "received",
            True,
            marks=pytest.mark.xfail(
                reason=(
                    "When we serialize a notification with status `returned-letter`, we display it as `received` "
                    "instead. But we don't currently do the inverse when filtering on `received`. We probably should, "
                    "but it would be a backwards-incompatible change and so may need flagging with API users before "
                    "we fix this."
                )
            ),
        ),
        ("created", "received", 0),
        ("sending", "received", 0),
        ("delivered", "accepted", 0),
    ),
)
def test_get_letter_notifications_filter_by_single_status(
    api_client_request, sample_letter_template, letter_rate, internal_status, filter_status, expect_num_notifications
):
    # the internal notification status `delivered` is mapped to `received` externally.
    notification = create_notification(template=sample_letter_template, status=internal_status)

    json_response = api_client_request.get(
        notification.service_id,
        "v2_notifications.get_notifications",
        status=filter_status,
    )

    assert json_response["links"]["current"].endswith(f"/v2/notifications?status={filter_status}")
    assert len(json_response["notifications"]) == expect_num_notifications

    if expect_num_notifications > 0:
        assert "next" in json_response["links"].keys()
        assert json_response["notifications"][0]["id"] == str(notification.id)
        assert json_response["notifications"][0]["status"] == filter_status


def test_get_all_notifications_filter_by_status_invalid_status(api_client_request, sample_notification):
    json_response = api_client_request.get(
        sample_notification.service_id, "v2_notifications.get_notifications", status="elephant", _expected_status=400
    )

    assert json_response["status_code"] == 400
    assert len(json_response["errors"]) == 1
    assert (
        json_response["errors"][0]["message"] == "status elephant is not one of [cancelled, created, sending, "
        "sent, delivered, pending, failed, technical-failure, temporary-failure, permanent-failure, "
        "pending-virus-check, validation-failed, virus-scan-failed, returned-letter, accepted, received]"
    )


def test_get_all_notifications_filter_by_multiple_statuses(api_client_request, sample_template, sms_rate):
    notifications = [
        create_notification(template=sample_template, status=_status) for _status in ["created", "pending", "sending"]
    ]
    failed_notification = create_notification(template=sample_template, status="permanent-failure")

    json_response = api_client_request.get(
        sample_template.service_id, "v2_notifications.get_notifications", status=["created", "pending", "sending"]
    )

    assert json_response["links"]["current"].endswith("/v2/notifications?status=created&status=pending&status=sending")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 3

    returned_notification_ids = [_n["id"] for _n in json_response["notifications"]]
    for _id in [_notification.id for _notification in notifications]:
        assert str(_id) in returned_notification_ids

    assert failed_notification.id not in returned_notification_ids


def test_get_all_notifications_filter_by_failed_status(api_client_request, sample_template, sms_rate):
    created_notification = create_notification(template=sample_template, status="created")
    failed_notifications = [
        create_notification(template=sample_template, status=_status)
        for _status in ["technical-failure", "temporary-failure", "permanent-failure"]
    ]

    json_response = api_client_request.get(
        sample_template.service_id, "v2_notifications.get_notifications", status="failed"
    )

    assert json_response["links"]["current"].endswith("/v2/notifications?status=failed")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 3

    returned_notification_ids = [n["id"] for n in json_response["notifications"]]
    for _id in [_notification.id for _notification in failed_notifications]:
        assert str(_id) in returned_notification_ids

    assert created_notification.id not in returned_notification_ids


def test_get_all_notifications_filter_by_id(api_client_request, sample_template, sms_rate):
    older_notification = create_notification(template=sample_template)
    newer_notification = create_notification(template=sample_template)

    json_response = api_client_request.get(
        sample_template.service_id, "v2_notifications.get_notifications", older_than=newer_notification.id
    )

    assert json_response["links"]["current"].endswith(f"/v2/notifications?older_than={newer_notification.id}")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(older_notification.id)


def test_get_all_notifications_filter_by_id_invalid_id(api_client_request, sample_notification):
    json_response = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_notifications",
        older_than="1234-badly-formatted-id-7890",
        _expected_status=400,
    )

    assert json_response["status_code"] == 400
    assert len(json_response["errors"]) == 1
    assert json_response["errors"][0]["message"] == "older_than is not a valid UUID"


def test_get_all_notifications_filter_by_id_no_notifications_if_nonexistent_id(api_client_request, sample_template):
    notification = create_notification(template=sample_template)

    json_response = api_client_request.get(
        notification.service_id,
        "v2_notifications.get_notifications",
        older_than="dd4b8b9d-d414-4a83-9256-580046bf18f9",
    )

    assert json_response["links"]["current"].endswith(
        "/v2/notifications?older_than=dd4b8b9d-d414-4a83-9256-580046bf18f9"
    )
    assert "next" not in json_response["links"].keys()
    assert len(json_response["notifications"]) == 0


def test_get_all_notifications_filter_by_id_no_notifications_if_last_notification(api_client_request, sample_template):
    notification = create_notification(template=sample_template)

    json_response = api_client_request.get(
        notification.service_id,
        "v2_notifications.get_notifications",
        older_than=notification.id,
    )

    assert json_response["links"]["current"].endswith(f"/v2/notifications?older_than={notification.id}")
    assert "next" not in json_response["links"].keys()
    assert len(json_response["notifications"]) == 0


def test_get_all_notifications_filter_multiple_query_parameters(api_client_request, sample_email_template):
    # this is the notification we are looking for
    older_notification = create_notification(template=sample_email_template, status="pending")

    # wrong status
    create_notification(template=sample_email_template)
    wrong_template = create_template(sample_email_template.service, template_type="sms")
    # wrong template
    create_notification(template=wrong_template, status="pending")

    # we only want notifications created before this one
    newer_notification = create_notification(template=sample_email_template)

    # this notification was created too recently
    create_notification(template=sample_email_template, status="pending")

    json_response = api_client_request.get(
        newer_notification.service_id,
        "v2_notifications.get_notifications",
        status="pending",
        template_type="email",
        older_than=newer_notification.id,
    )

    # query parameters aren't returned in order
    for url_part in [
        "/v2/notifications?",
        "template_type=email",
        "status=pending",
        f"older_than={newer_notification.id}",
    ]:
        assert url_part in json_response["links"]["current"]

    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["id"] == str(older_notification.id)


def test_get_all_notifications_renames_letter_statuses(
    api_client_request,
    sample_letter_notification,
    sample_notification,
    sample_email_notification,
    letter_rate,
):
    json_response = api_client_request.get(
        sample_letter_notification.service_id,
        "v2_notifications.get_notifications",
    )

    for noti in json_response["notifications"]:
        if noti["type"] == "sms" or noti["type"] == "email":
            assert noti["status"] == "created"
        elif noti["type"] == "letter":
            assert noti["status"] == "accepted"
        else:
            pytest.fail()


def test_get_all_notifications_returns_cost_datarmation(api_client_request, sample_template, sms_rate):
    notification = create_notification(template=sample_template)

    json_response = api_client_request.get(notification.service_id, "v2_notifications.get_notifications")

    assert json_response["links"]["current"].endswith("/v2/notifications")
    assert "next" in json_response["links"].keys()
    assert len(json_response["notifications"]) == 1

    assert json_response["notifications"][0]["cost_in_pounds"] == 0.0227
    assert json_response["notifications"][0]["cost_details"] == {
        "billable_sms_fragments": 1,
        "international_rate_multiplier": 1,
        "sms_rate": 0.0227,
    }


@pytest.mark.parametrize(
    "db_status,expected_status",
    [
        ("created", "accepted"),
        ("sending", "accepted"),
        ("delivered", "received"),
        ("pending", "pending"),
        ("technical-failure", "technical-failure"),
    ],
)
def test_get_notification_by_id_renames_letter_statuses(
    api_client_request, sample_letter_template, letter_rate, db_status, expected_status
):
    letter_noti = create_notification(
        sample_letter_template,
        status=db_status,
        personalisation={"address_line_1": "Mr Foo", "address_line_2": "1 Bar Street", "postcode": "N1"},
    )

    json_response = api_client_request.get(
        letter_noti.service_id, "v2_notifications.get_notification_by_id", notification_id=letter_noti.id
    )

    assert json_response["status"] == expected_status


def test_get_pdf_for_notification_returns_pdf_content(
    client,
    sample_letter_notification,
    mocker,
):
    mock_get_letter_pdf = mocker.patch(
        "app.v2.notifications.get_notifications.get_letter_pdf_and_metadata",
        return_value=(b"foo", {"message": "", "invalid_pages": "", "page_count": "1"}),
    )
    sample_letter_notification.status = "created"

    auth_header = create_service_authorization_header(service_id=sample_letter_notification.service_id)
    response = client.get(
        path=url_for("v2_notifications.get_pdf_for_notification", notification_id=sample_letter_notification.id),
        headers=[("Content-Type", "application/json"), auth_header],
    )

    assert response.status_code == 200
    assert response.get_data() == b"foo"
    mock_get_letter_pdf.assert_called_once_with(sample_letter_notification)


def test_get_pdf_for_notification_returns_400_if_pdf_not_found(
    api_client_request,
    sample_letter_notification,
    mocker,
):
    # if no files are returned get_letter_pdf throws StopIteration as the iterator runs out
    mock_get_letter_pdf = mocker.patch(
        "app.v2.notifications.get_notifications.get_letter_pdf_and_metadata", side_effect=(StopIteration, {})
    )
    sample_letter_notification.status = "created"

    response_json = api_client_request.get(
        sample_letter_notification.service_id,
        "v2_notifications.get_pdf_for_notification",
        notification_id=sample_letter_notification.id,
        _expected_status=400,
    )

    assert response_json["errors"] == [
        {"error": "PDFNotReadyError", "message": "PDF not available yet, try again later"}
    ]
    mock_get_letter_pdf.assert_called_once_with(sample_letter_notification)


@pytest.mark.parametrize(
    "status, expected_message",
    [
        ("virus-scan-failed", "File did not pass the virus scan"),
        ("technical-failure", "PDF not available for letters in status technical-failure"),
    ],
)
def test_get_pdf_for_notification_only_returns_pdf_content_if_right_status(
    api_client_request, sample_letter_notification, mocker, status, expected_message
):
    mock_get_letter_pdf = mocker.patch(
        "app.v2.notifications.get_notifications.get_letter_pdf_and_metadata",
        return_value=(b"foo", {"message": "", "invalid_pages": "", "page_count": "1"}),
    )
    sample_letter_notification.status = status

    response_json = api_client_request.get(
        sample_letter_notification.service_id,
        "v2_notifications.get_pdf_for_notification",
        notification_id=sample_letter_notification.id,
        _expected_status=400,
    )

    assert response_json["errors"] == [{"error": "BadRequestError", "message": expected_message}]
    assert mock_get_letter_pdf.called is False


def test_get_pdf_for_notification_fails_for_non_letters(api_client_request, sample_notification):
    response_json = api_client_request.get(
        sample_notification.service_id,
        "v2_notifications.get_pdf_for_notification",
        notification_id=sample_notification.id,
        _expected_status=400,
    )
    assert response_json["errors"] == [{"error": "BadRequestError", "message": "Notification is not a letter"}]
