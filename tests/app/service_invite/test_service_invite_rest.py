import json
import uuid

import pytest
from flask import current_app
from freezegun import freeze_time
from notifications_utils.url_safe_token import generate_token

from app.constants import EMAIL_AUTH_TYPE, SMS_AUTH_TYPE
from app.models import Notification
from tests import create_admin_authorization_header
from tests.app.db import create_invited_user, create_permissions, create_service, create_user


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
        "/service/{}/invite".format(sample_service.id),
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
    for i in range(0, 5):
        email = "invited_user_{}@service.gov.uk".format(i)
        invited_user = create_invited_user(sample_service, to_email_address=email)

        invites.append(invited_user)

    url = "/service/{}/invite".format(sample_service.id)

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
    url = "/service/{}/invite".format(sample_service.id)

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
    url = "/service/{0}/invite/{1}".format(sample_invited_user.service_id, sample_invited_user.id)
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[("Content-Type", "application/json"), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))["data"]
    assert json_resp["status"] == "cancelled"


def test_update_invited_user_for_wrong_service_returns_404(client, sample_invited_user, fake_uuid):
    data = {"status": "cancelled"}
    url = "/service/{0}/invite/{1}".format(fake_uuid, sample_invited_user.id)
    auth_header = create_admin_authorization_header()
    response = client.post(url, data=json.dumps(data), headers=[("Content-Type", "application/json"), auth_header])
    assert response.status_code == 404
    json_response = json.loads(response.get_data(as_text=True))["message"]
    assert json_response == "No result found"


def test_update_invited_user_for_invalid_data_returns_400(client, sample_invited_user):
    data = {"status": "garbage"}
    url = "/service/{0}/invite/{1}".format(sample_invited_user.service_id, sample_invited_user.id)
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
    url = "/invite/service/{}".format(token)
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
    url = "/invite/service/{}".format(token)
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

    url = "/invite/service/{}".format(token)
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


def test_get_invited_user_404s_if_invite_doesnt_exist(admin_request, sample_invited_user, fake_uuid):
    json_resp = admin_request.get("service_invite.get_invited_user", invited_user_id=fake_uuid, _expected_status=404)
    assert json_resp["result"] == "error"


@pytest.mark.parametrize(
    "reason, expected_reason_given, expected_reason",
    (
        (
            "",
            "no",
            "",
        ),
        (
            "One reason given",
            "yes",
            "^ One reason given",
        ),
        (
            "Lots of reasons\n\nIncluding more in a new paragraph",
            "yes",
            "^ Lots of reasons\n^ \n^ Including more in a new paragraph",
        ),
    ),
)
def test_request_invite_to_service_email_is_sent_to_valid_service_managers(
    admin_request,
    notify_service,
    sample_service,
    request_invite_email_template,
    receipt_for_request_invite_email_template,
    mocker,
    reason,
    expected_reason_given,
    expected_reason,
):
    # This test also covers a scenario where a list that contains valid service managers also contains an invalid
    # service manager. Expected behaviour is that notifications will be sent only to the valid service managers.
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    user_requesting_invite = create_user()
    service_manager_1 = create_user(name="Manager 1", email_address="manager.1@example.gov.uk")
    service_manager_2 = create_user(name="Manager 2", email_address="manager.2@example.gov.uk")
    service_manager_3 = create_user(name="Manager 3", email_address="manager.3@example.gov.uk")
    another_service = create_service(service_name="Another Service")
    service_manager_1.services = [sample_service]
    service_manager_2.services = [sample_service]
    service_manager_3.services = [another_service]
    create_permissions(service_manager_1, sample_service, "manage_settings")
    create_permissions(service_manager_2, sample_service, "manage_settings")
    create_permissions(service_manager_3, another_service, "manage_settings")
    recipients_of_invite_request = [service_manager_1.id, service_manager_2.id, service_manager_3.id]
    invite_link_host = current_app.config["ADMIN_BASE_URL"]

    data = dict(
        service_managers_ids=list(map(lambda x: str(x), recipients_of_invite_request)),
        reason=reason,
        invite_link_host=invite_link_host,
    )
    admin_request.post(
        "service_invite.request_invite_to_service",
        service_id=sample_service.id,
        user_to_invite_id=user_requesting_invite.id,
        _data=data,
        _expected_status=204,
    )

    # Two sets of notifications are sent:
    # 1.request invite notifications to the service manager(s)
    # 2.receipt for request invite notification to the user that initiated the invite request.

    notifications = Notification.query.all()
    manager_notification = [n for n in notifications if n.personalisation["name"] == service_manager_1.name][0]
    user_notification = [n for n in notifications if n.personalisation["name"] == user_requesting_invite.name][0]

    mocked.call_count = 3
    assert len(notifications) == 3

    # Request invite notification
    assert len(manager_notification.personalisation.keys()) == 7
    assert manager_notification.personalisation["requester_name"] == user_requesting_invite.name
    assert manager_notification.personalisation["service_name"] == sample_service.name
    assert manager_notification.personalisation["reason_given"] == expected_reason_given
    assert manager_notification.personalisation["reason"] == expected_reason
    assert (
        manager_notification.personalisation["url"]
        == f"{invite_link_host}/services/{sample_service.id}/users/invite/{user_requesting_invite.id}"
    )
    assert manager_notification.reply_to_text == user_requesting_invite.email_address

    # Receipt for request invite notification
    assert user_notification.personalisation == {
        "name": user_requesting_invite.name,
        "service name": "Sample service",
        "service admin names": [
            "Manager 1 – manager.1@example.gov.uk",
            "Manager 2 – manager.2@example.gov.uk",
            "Manager 3 – manager.3@example.gov.uk",
        ],
        "request again url": f"{invite_link_host}/services/{sample_service.id}/join",
    }
    assert user_notification.reply_to_text == "notify@gov.uk"


def test_request_invite_to_service_email_is_not_sent_if_requester_is_already_part_of_service(
    admin_request, sample_service
):
    user_requesting_invite = create_user()
    user_requesting_invite.services = [sample_service]
    service_manager_1 = create_user()
    create_permissions(service_manager_1, sample_service)
    service_managers = [service_manager_1]
    reason = "Lots of reasons"
    invite_link_host = current_app.config["ADMIN_BASE_URL"]
    data = dict(
        service_managers_ids=list(map(lambda x: str(x.id), service_managers)),
        reason=reason,
        invite_link_host=invite_link_host,
    )

    admin_request.post(
        "service_invite.request_invite_to_service",
        service_id=sample_service.id,
        user_to_invite_id=user_requesting_invite.id,
        _data=data,
        _expected_status=400,
    )


def test_exception_is_raised_if_no_request_invite_to_service_email_is_sent(
    admin_request,
    notify_service,
    sample_service,
    request_invite_email_template,
    receipt_for_request_invite_email_template,
):
    user_requesting_invite = create_user()
    service_manager = create_user()
    another_service = create_service(service_name="Another Service")
    service_manager.services = [another_service]
    create_permissions(service_manager, another_service, "manage_settings")
    recipients_of_invite_request = [service_manager.id]
    reason = "Lots of reasons"
    invite_link_host = current_app.config["ADMIN_BASE_URL"]
    data = dict(
        service_managers_ids=list(map(lambda x: str(x), recipients_of_invite_request)),
        reason=reason,
        invite_link_host=invite_link_host,
    )

    admin_request.post(
        "service_invite.request_invite_to_service",
        service_id=sample_service.id,
        user_to_invite_id=user_requesting_invite.id,
        _data=data,
        _expected_status=400,
    )
