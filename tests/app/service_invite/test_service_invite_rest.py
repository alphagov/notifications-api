import json
import uuid

import pytest
from flask import current_app
from freezegun import freeze_time
from notifications_utils.url_safe_token import generate_token

from app.constants import EMAIL_AUTH_TYPE, SMS_AUTH_TYPE
from app.models import Notification
from tests import create_admin_authorization_header
from tests.app.db import create_invited_user


@pytest.mark.parametrize(
    "extra_args, expected_start_of_invite_url",
    [
        ({}, "{hostnames.admin}/invitation/"),
        ({"invite_link_host": "https://www.example.com"}, "https://www.example.com/invitation/"),
    ],
)
def test_create_invited_user(
    admin_request,
    sample_service,
    mocker,
    invitation_email_template,
    extra_args,
    expected_start_of_invite_url,
    hostnames,
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    email_address = "invited_user@service.gov.uk"
    invite_from = sample_service.users[0]

    data = dict(
        service=str(sample_service.id),
        email_address=email_address,
        from_user=str(invite_from.id),
        permissions="send_messages,manage_service,manage_api_keys",
        auth_type=EMAIL_AUTH_TYPE,
        folder_permissions=["folder_1", "folder_2", "folder_3"],
        **extra_args,
    )

    json_resp = admin_request.post(
        "service_invite.create_invited_user", service_id=sample_service.id, _data=data, _expected_status=201
    )

    assert json_resp["data"]["service"] == str(sample_service.id)
    assert json_resp["data"]["email_address"] == email_address
    assert json_resp["data"]["from_user"] == str(invite_from.id)
    assert json_resp["data"]["permissions"] == "send_messages,manage_service,manage_api_keys"
    assert json_resp["data"]["auth_type"] == EMAIL_AUTH_TYPE
    assert json_resp["data"]["id"]
    assert json_resp["data"]["folder_permissions"] == ["folder_1", "folder_2", "folder_3"]

    notification = Notification.query.first()

    assert notification.reply_to_text == invite_from.email_address

    assert len(notification.personalisation.keys()) == 3
    assert notification.personalisation["service_name"] == "Sample service"
    assert notification.personalisation["user_name"] == "Test User"
    assert notification.personalisation["url"].startswith(expected_start_of_invite_url.format(hostnames=hostnames))
    assert len(notification.personalisation["url"]) > len(expected_start_of_invite_url.format(hostnames=hostnames))
    assert str(notification.template_id) == current_app.config["INVITATION_EMAIL_TEMPLATE_ID"]

    mocked.assert_called_once_with([(str(notification.id))], queue="notify-internal-tasks")


def test_create_invited_user_without_auth_type(admin_request, sample_service, mocker, invitation_email_template):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    email_address = "invited_user@service.gov.uk"
    invite_from = sample_service.users[0]

    data = {
        "service": str(sample_service.id),
        "email_address": email_address,
        "from_user": str(invite_from.id),
        "permissions": "send_messages,manage_service,manage_api_keys",
        "folder_permissions": [],
    }

    json_resp = admin_request.post(
        "service_invite.create_invited_user", service_id=sample_service.id, _data=data, _expected_status=201
    )

    assert json_resp["data"]["auth_type"] == SMS_AUTH_TYPE


def test_create_invited_user_invalid_email(client, sample_service, mocker, fake_uuid):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    email_address = "notanemail"
    invite_from = sample_service.users[0]

    data = {
        "service": str(sample_service.id),
        "email_address": email_address,
        "from_user": str(invite_from.id),
        "permissions": "send_messages,manage_service,manage_api_keys",
        "folder_permissions": [fake_uuid, fake_uuid],
    }

    data = json.dumps(data)

    auth_header = create_admin_authorization_header()

    response = client.post(
        f"/service/{sample_service.id}/invite",
        headers=[("Content-Type", "application/json"), auth_header],
        data=data,
    )
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {"email_address": ["Not a valid email address"]}
    assert mocked.call_count == 0


def test_get_all_invited_users_by_service(client, notify_db_session, sample_service):
    invites = []
    for i in range(5):
        email = f"invited_user_{i}@service.gov.uk"
        invited_user = create_invited_user(sample_service, to_email_address=email)

        invites.append(invited_user)

    url = f"/service/{sample_service.id}/invite"

    auth_header = create_admin_authorization_header()

    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    invite_from = sample_service.users[0]

    for invite in json_resp["data"]:
        assert invite["service"] == str(sample_service.id)
        assert invite["from_user"] == str(invite_from.id)
        assert invite["auth_type"] == SMS_AUTH_TYPE
        assert invite["id"]


def test_get_invited_users_by_service_with_no_invites(client, notify_db_session, sample_service):
    url = f"/service/{sample_service.id}/invite"

    auth_header = create_admin_authorization_header()

    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp["data"]) == 0


def test_get_invited_user_by_service(admin_request, sample_invited_user):
    json_resp = admin_request.get(
        "service_invite.get_invited_user_by_service",
        service_id=sample_invited_user.service.id,
        invited_user_id=sample_invited_user.id,
    )
    assert json_resp["data"]["email_address"] == sample_invited_user.email_address


def test_get_invited_user_by_service_when_user_does_not_belong_to_the_service(
    admin_request,
    sample_invited_user,
    fake_uuid,
):
    json_resp = admin_request.get(
        "service_invite.get_invited_user_by_service",
        service_id=fake_uuid,
        invited_user_id=sample_invited_user.id,
        _expected_status=404,
    )
    assert json_resp["result"] == "error"


def test_update_invited_user_set_status_to_cancelled(client, sample_invited_user):
    data = {"status": "cancelled"}
    url = f"/service/{sample_invited_user.service_id}/invite/{sample_invited_user.id}"
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))["data"]
    assert json_resp["status"] == "cancelled"


def test_update_invited_user_for_wrong_service_returns_404(client, sample_invited_user, fake_uuid):
    data = {"status": "cancelled"}
    url = f"/service/{fake_uuid}/invite/{sample_invited_user.id}"
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[("Content-Type", "application/json"), auth_header])
    assert response.status_code == 404
    json_response = json.loads(response.get_data(as_text=True))["message"]
    assert json_response == "No result found"


def test_update_invited_user_for_invalid_data_returns_400(client, sample_invited_user):
    data = {"status": "garbage"}
    url = f"/service/{sample_invited_user.service_id}/invite/{sample_invited_user.id}"
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[("Content-Type", "application/json"), auth_header])
    assert response.status_code == 400


@pytest.mark.parametrize(
    "endpoint_format_str",
    [
        "/invite/service/{}",
        "/invite/service/check/{}",
    ],
)
def test_validate_invitation_token_returns_200_when_token_valid(client, sample_invited_user, endpoint_format_str):
    token = generate_token(
        str(sample_invited_user.id), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
    )
    url = endpoint_format_str.format(token)
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["data"]["id"] == str(sample_invited_user.id)
    assert json_resp["data"]["email_address"] == sample_invited_user.email_address
    assert json_resp["data"]["from_user"] == str(sample_invited_user.user_id)
    assert json_resp["data"]["service"] == str(sample_invited_user.service_id)
    assert json_resp["data"]["status"] == sample_invited_user.status
    assert json_resp["data"]["permissions"] == sample_invited_user.permissions
    assert json_resp["data"]["folder_permissions"] == sample_invited_user.folder_permissions


def test_validate_invitation_token_for_expired_token_returns_400(client):
    with freeze_time("2016-01-01T12:00:00"):
        token = generate_token(
            str(uuid.uuid4()), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
        )
    url = f"/invite/service/{token}"
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {
        "invitation": "Your invitation to GOV.UK Notify has expired. "
        "Please ask the person that invited you to send you another one"
    }


def test_validate_invitation_token_returns_400_when_invited_user_does_not_exist(client):
    token = generate_token(str(uuid.uuid4()), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])
    url = f"/invite/service/{token}"
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == "No result found"


def test_validate_invitation_token_returns_400_when_token_is_malformed(client):
    token = generate_token(str(uuid.uuid4()), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])[
        :-2
    ]

    url = f"/invite/service/{token}"
    auth_header = create_admin_authorization_header()
    response = client.get(url, headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["result"] == "error"
    assert json_resp["message"] == {
        "invitation": "Something’s wrong with this link. Make sure you’ve copied the whole thing."
    }


def test_get_invited_user(admin_request, sample_invited_user):
    json_resp = admin_request.get("service_invite.get_invited_user", invited_user_id=sample_invited_user.id)
    assert json_resp["data"]["id"] == str(sample_invited_user.id)
    assert json_resp["data"]["email_address"] == sample_invited_user.email_address
    assert json_resp["data"]["service"] == str(sample_invited_user.service_id)
    assert json_resp["data"]["permissions"] == sample_invited_user.permissions


def test_get_invited_user_404s_if_invite_doesnt_exist(admin_request, fake_uuid):
    json_resp = admin_request.get("service_invite.get_invited_user", invited_user_id=fake_uuid, _expected_status=404)
    assert json_resp["result"] == "error"
