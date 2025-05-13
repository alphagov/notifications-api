import pytest
from freezegun import freeze_time
from notifications_utils.s3 import S3ObjectNotFound

from app.constants import EMAIL_TYPE, LETTER_TYPE, UPLOAD_LETTERS
from app.dao.notifications_dao import get_notification_by_id
from app.service.send_notification import send_pdf_letter_notification
from app.v2.errors import BadRequestError, TooManyRequestsError
from tests.app.db import create_service, create_template


@pytest.fixture
def post_data(sample_service_full_permissions, fake_uuid):
    return {
        "filename": "valid.pdf",
        "created_by": sample_service_full_permissions.users[0].id,
        "file_id": fake_uuid,
        "postage": "second",
        "recipient_address": "Bugs%20Bunny%0A123%20Main%20Street%0ALooney%20Town",
    }


@pytest.mark.parametrize(
    "permissions",
    [
        [EMAIL_TYPE],
        [UPLOAD_LETTERS],
    ],
)
def test_send_pdf_letter_notification_raises_error_if_service_does_not_have_permission(
    notify_db_session,
    permissions,
    post_data,
):
    service = create_service(service_permissions=permissions)

    with pytest.raises(BadRequestError):
        send_pdf_letter_notification(service.id, post_data)


def test_send_pdf_letter_notification_raises_error_if_using_economy_postage_without_permission(
    sample_service,
    post_data,
):
    create_template(
        sample_service,
        template_type=LETTER_TYPE,
        template_name="Pre-compiled PDF",
        hidden=True,
    )

    post_data["postage"] = "economy"
    post_data["created_by"] = sample_service.users[0].id

    with pytest.raises(BadRequestError):
        send_pdf_letter_notification(sample_service.id, post_data)


def test_send_pdf_letter_notification_raises_error_if_service_is_over_daily_message_limit(
    mocker,
    sample_service_full_permissions,
    post_data,
):
    mock_check_message_limit = mocker.patch(
        "app.service.send_notification.check_service_over_daily_message_limit",
        side_effect=TooManyRequestsError("total", 10),
    )

    with pytest.raises(TooManyRequestsError):
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)

    assert mock_check_message_limit.call_args_list == [
        mocker.call(sample_service_full_permissions, "normal", notification_type=LETTER_TYPE)
    ]


def test_send_pdf_letter_notification_validates_created_by(sample_service_full_permissions, sample_user, post_data):
    post_data["created_by"] = sample_user.id

    with pytest.raises(BadRequestError):
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)


def test_send_pdf_letter_notification_raises_error_if_service_in_trial_mode(
    sample_service_full_permissions,
    post_data,
):
    sample_service_full_permissions.restricted = True

    with pytest.raises(BadRequestError) as e:
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)
    assert "trial mode" in e.value.message


def test_send_pdf_letter_notification_raises_error_when_pdf_is_not_in_transient_letter_bucket(
    mocker,
    sample_service_full_permissions,
    notify_user,
    post_data,
):
    mocker.patch("app.service.send_notification.utils_s3download", side_effect=S3ObjectNotFound({}, ""))

    with pytest.raises(S3ObjectNotFound):
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)


def test_send_pdf_letter_notification_does_nothing_if_notification_already_exists(
    mocker,
    sample_service_full_permissions,
    notify_user,
    sample_notification,
    post_data,
):
    post_data["file_id"] = sample_notification.id
    mocker.patch("app.service.send_notification.utils_s3download", side_effect=S3ObjectNotFound({}, ""))
    response = send_pdf_letter_notification(sample_service_full_permissions.id, post_data)
    assert response["id"] == str(sample_notification.id)


@freeze_time("2019-08-02 11:00:00")
def test_send_pdf_letter_notification_creates_notification_and_moves_letter(
    mocker,
    sample_service_full_permissions,
    notify_user,
    post_data,
):
    mocker.patch("app.service.send_notification.utils_s3download")
    mocker.patch("app.service.send_notification.get_page_count", return_value=1)
    s3_mock = mocker.patch("app.service.send_notification.move_uploaded_pdf_to_letters_bucket")

    result = send_pdf_letter_notification(sample_service_full_permissions.id, post_data)
    file_id = post_data["file_id"]

    notification = get_notification_by_id(file_id)

    assert str(notification.id) == file_id
    assert notification.api_key_id is None
    assert notification.client_reference == post_data["filename"]
    assert notification.created_by_id == post_data["created_by"]
    assert notification.postage == "second"
    assert notification.notification_type == LETTER_TYPE
    assert notification.billable_units == 1
    assert notification.to == "Bugs Bunny\n123 Main Street\nLooney Town"

    assert notification.service_id == sample_service_full_permissions.id
    assert result == {"id": str(notification.id)}

    s3_mock.assert_called_once_with(
        f"service-{sample_service_full_permissions.id}/{file_id}.pdf",
        f"2019-08-02/NOTIFY.{notification.reference}.D.2.C.20190802110000.PDF",
    )
