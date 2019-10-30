import uuid

import pytest
from freezegun import freeze_time

from app.dao.notifications_dao import get_notification_by_id
from app.models import EMAIL_TYPE, LETTER_TYPE, UPLOAD_LETTERS
from app.service.send_notification import send_pdf_letter_notification
from app.v2.errors import BadRequestError, TooManyRequestsError
from notifications_utils.s3 import S3ObjectNotFound
from tests.app.db import create_service


@pytest.mark.parametrize('permissions', [
    [EMAIL_TYPE],
    [LETTER_TYPE],
    [UPLOAD_LETTERS],
])
def test_send_pdf_letter_notification_raises_error_if_service_does_not_have_permission(
    notify_db_session,
    fake_uuid,
    permissions,
):
    service = create_service(service_permissions=permissions)
    post_data = {'filename': 'valid.pdf', 'created_by': fake_uuid, 'file_id': fake_uuid, 'postage': 'first'}

    with pytest.raises(BadRequestError):
        send_pdf_letter_notification(service.id, post_data)


def test_send_pdf_letter_notification_raises_error_if_service_is_over_daily_message_limit(
    mocker,
    sample_service_full_permissions,
    fake_uuid,
):
    mocker.patch(
        'app.service.send_notification.check_service_over_daily_message_limit',
        side_effect=TooManyRequestsError(10))
    post_data = {'filename': 'valid.pdf', 'created_by': fake_uuid, 'file_id': fake_uuid, 'postage': 'first'}

    with pytest.raises(TooManyRequestsError):
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)


def test_send_pdf_letter_notification_validates_created_by(
    sample_service_full_permissions, fake_uuid, sample_user
):
    post_data = {'filename': 'valid.pdf', 'created_by': sample_user.id, 'file_id': fake_uuid, 'postage': 'first'}

    with pytest.raises(BadRequestError):
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)


def test_send_pdf_letter_notification_raises_error_if_service_in_trial_mode(
    mocker,
    sample_service_full_permissions,
    fake_uuid,
):
    sample_service_full_permissions.restricted = True
    user = sample_service_full_permissions.users[0]
    post_data = {'filename': 'valid.pdf', 'created_by': user.id, 'file_id': fake_uuid}

    with pytest.raises(BadRequestError) as e:
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)
    assert 'trial mode' in e.value.message


def test_send_pdf_letter_notification_raises_error_when_pdf_is_not_in_transient_letter_bucket(
    mocker,
    sample_service_full_permissions,
    fake_uuid,
    notify_user,
):
    user = sample_service_full_permissions.users[0]
    post_data = {'filename': 'valid.pdf', 'created_by': user.id, 'file_id': fake_uuid, 'postage': 'first'}
    mocker.patch('app.service.send_notification.utils_s3download', side_effect=S3ObjectNotFound({}, ''))

    with pytest.raises(S3ObjectNotFound):
        send_pdf_letter_notification(sample_service_full_permissions.id, post_data)


@freeze_time("2019-08-02 11:00:00")
def test_send_pdf_letter_notification_creates_notification_and_moves_letter(
    mocker,
    sample_service_full_permissions,
    notify_user,
):
    user = sample_service_full_permissions.users[0]
    filename = 'valid.pdf'
    file_id = uuid.uuid4()
    post_data = {'filename': filename, 'created_by': user.id, 'file_id': file_id, 'postage': 'second'}

    mocker.patch('app.service.send_notification.utils_s3download')
    mocker.patch('app.service.send_notification.get_page_count', return_value=1)
    s3_mock = mocker.patch('app.service.send_notification.move_uploaded_pdf_to_letters_bucket')

    result = send_pdf_letter_notification(sample_service_full_permissions.id, post_data)

    notification = get_notification_by_id(file_id)

    assert notification.id == file_id
    assert notification.api_key_id is None
    assert notification.client_reference == filename
    assert notification.created_by_id == user.id
    assert notification.postage == 'second'
    assert notification.notification_type == LETTER_TYPE
    assert notification.billable_units == 1
    assert notification.to == filename
    assert notification.service_id == sample_service_full_permissions.id

    assert result == {'id': str(notification.id)}

    s3_mock.assert_called_once_with(
        'service-{}/{}.pdf'.format(sample_service_full_permissions.id, file_id),
        '2019-08-02/NOTIFY.{}.D.2.C.C.20190802110000.PDF'.format(notification.reference)
    )
