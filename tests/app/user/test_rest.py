import uuid
from datetime import datetime
from unittest import mock

import pytest
from flask import current_app, url_for
from freezegun import freeze_time

from app.constants import (
    EMAIL_AUTH_TYPE,
    MANAGE_SETTINGS,
    MANAGE_TEMPLATES,
    SMS_AUTH_TYPE,
    OrganisationUserPermissionTypes,
)
from app.dao.organisation_user_permissions_dao import organisation_user_permissions_dao
from app.dao.permissions_dao import default_service_permissions
from app.dao.service_user_dao import (
    dao_get_service_user,
    dao_update_service_user,
)
from app.models import Notification, OrganisationUserPermissions, Permission, User
from app.utils import DATETIME_FORMAT
from tests import create_admin_authorization_header, create_service_authorization_header
from tests.app.db import (
    create_organisation,
    create_service,
    create_template_folder,
    create_user,
    create_webauthn_credential,
)


def test_get_user(admin_request, sample_service, sample_organisation):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single user.
    """
    sample_user = sample_service.users[0]
    sample_user.organisations = [sample_organisation]
    json_resp = admin_request.get("user.get_user", user_id=sample_user.id)

    expected_permissions = default_service_permissions
    fetched = json_resp["data"]

    assert len(fetched) == 20

    assert fetched["id"] == str(sample_user.id)
    assert fetched["name"] == sample_user.name
    assert fetched["email_address"] == sample_user.email_address
    assert fetched["created_at"] == sample_user.created_at.strftime(DATETIME_FORMAT)
    assert fetched["auth_type"] == SMS_AUTH_TYPE
    assert fetched["current_session_id"] is None
    assert fetched["failed_login_count"] == 0
    assert fetched["email_access_validated_at"]
    assert fetched["logged_in_at"] is None
    assert fetched["mobile_number"] == sample_user.mobile_number
    assert fetched["organisations"] == [str(sample_organisation.id)]
    assert fetched["password_changed_at"]
    assert fetched["permissions"].keys() == {str(sample_service.id)}
    assert sorted(fetched["permissions"][str(sample_service.id)]) == sorted(expected_permissions)
    assert fetched["organisation_permissions"] == {str(sample_organisation.id): []}
    assert fetched["platform_admin"] is False
    assert fetched["services"] == [str(sample_service.id)]
    assert fetched["can_use_webauthn"] is False
    assert fetched["state"] == sample_user.state
    assert fetched["take_part_in_research"] is True
    assert fetched["receives_new_features_email"] is True


def test_get_user_doesnt_return_inactive_services_and_orgs(admin_request, sample_service, sample_organisation):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    sample_service.active = False
    sample_organisation.active = False

    sample_user = sample_service.users[0]
    sample_user.organisations = [sample_organisation]

    json_resp = admin_request.get("user.get_user", user_id=sample_user.id)

    fetched = json_resp["data"]

    assert fetched["id"] == str(sample_user.id)
    assert fetched["services"] == []
    assert fetched["organisations"] == []
    assert fetched["permissions"] == {}


def test_post_user(admin_request, notify_db_session):
    """
    Tests POST endpoint '/' to create a user.
    """
    User.query.delete()
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
        "auth_type": EMAIL_AUTH_TYPE,
    }
    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=201)

    user = User.query.filter_by(email_address="user@digital.cabinet-office.gov.uk").first()
    assert user.check_password("password")
    assert json_resp["data"]["email_address"] == user.email_address
    assert json_resp["data"]["id"] == str(user.id)
    assert user.auth_type == EMAIL_AUTH_TYPE


def test_post_user_without_auth_type(admin_request, notify_db_session):
    User.query.delete()
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": "+447700900986",
        "permissions": {},
    }

    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=201)

    user = User.query.filter_by(email_address="user@digital.cabinet-office.gov.uk").first()
    assert json_resp["data"]["id"] == str(user.id)
    assert user.auth_type == SMS_AUTH_TYPE


def test_post_user_missing_attribute_email(admin_request, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute email.
    """
    User.query.delete()
    data = {
        "name": "Test User",
        "password": "password",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
    }
    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=400)

    assert User.query.count() == 0
    assert {"email_address": ["Missing data for required field."]} == json_resp["message"]


def test_create_user_missing_attribute_password(admin_request, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute password.
    """
    User.query.delete()
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
    }
    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=400)
    assert User.query.count() == 0
    assert {"password": ["Missing data for required field."]} == json_resp["message"]


def test_can_create_user_with_email_auth_and_no_mobile(admin_request, notify_db_session):
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": None,
        "auth_type": EMAIL_AUTH_TYPE,
    }

    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=201)

    assert json_resp["data"]["auth_type"] == EMAIL_AUTH_TYPE
    assert json_resp["data"]["mobile_number"] is None


def test_cannot_create_user_with_sms_auth_and_no_mobile(admin_request, notify_db_session):
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": None,
        "auth_type": SMS_AUTH_TYPE,
    }

    json_resp = admin_request.post("user.create_user", _data=data, _expected_status=400)

    assert json_resp["message"] == "Mobile number must be set if auth_type is set to sms_auth"


def test_cannot_create_user_with_empty_strings(admin_request, notify_db_session):
    data = {"name": "", "email_address": "", "password": "password", "mobile_number": "", "auth_type": EMAIL_AUTH_TYPE}
    resp = admin_request.post("user.create_user", _data=data, _expected_status=400)
    assert resp["message"] == {
        "email_address": ["Not a valid email address"],
        "mobile_number": ["Invalid phone number: Not enough digits"],
        "name": ["Invalid name"],
    }


@pytest.mark.parametrize(
    "user_attribute, user_value",
    [
        ("name", "New User"),
        ("email_address", "newuser@mail.com"),
        ("mobile_number", "+4407700900460"),
        ("take_part_in_research", False),
        ("receives_new_features_email", False),
    ],
)
def test_post_user_attribute(admin_request, sample_user, user_attribute, user_value):
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {user_attribute: user_value}

    json_resp = admin_request.post("user.update_user_attribute", user_id=sample_user.id, _data=update_dict)

    assert json_resp["data"][user_attribute] == user_value
    assert getattr(sample_user, user_attribute) == user_value


@pytest.mark.parametrize(
    "user_attribute, user_value, arguments",
    [
        ("name", "New User", None),
        (
            "email_address",
            "newuser@mail.com",
            {
                "api_key_id": None,
                "key_type": "normal",
                "notification_type": "email",
                "personalisation": {
                    "name": "Test User",
                    "servicemanagername": "Service Manago",
                    "email address": "newuser@mail.com",
                },
                "recipient": "newuser@mail.com",
                "reply_to_text": "notify@gov.uk",
                "service": mock.ANY,
                "template_id": uuid.UUID("c73f1d71-4049-46d5-a647-d013bdeca3f0"),
                "template_version": 1,
            },
        ),
        (
            "mobile_number",
            "+4407700900460",
            {
                "api_key_id": None,
                "key_type": "normal",
                "notification_type": "sms",
                "personalisation": {
                    "name": "Test User",
                    "servicemanagername": "Service Manago",
                    "email address": "notify@digital.cabinet-office.gov.uk",
                },
                "recipient": "+4407700900460",
                "reply_to_text": "testing",
                "service": mock.ANY,
                "template_id": uuid.UUID("8a31520f-4751-4789-8ea1-fe54496725eb"),
                "template_version": 1,
            },
        ),
    ],
)
def test_post_user_attribute_with_updated_by(
    admin_request,
    mocker,
    sample_user,
    user_attribute,
    user_value,
    arguments,
    team_member_email_edit_template,
    team_member_mobile_edit_template,
):
    updater = create_user(name="Service Manago", email="notify_manago@digital.cabinet-office.gov.uk")
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {user_attribute: user_value, "updated_by": str(updater.id)}
    mock_persist_notification = mocker.patch("app.user.rest.persist_notification")
    mocker.patch("app.user.rest.send_notification_to_queue")
    json_resp = admin_request.post("user.update_user_attribute", user_id=sample_user.id, _data=update_dict)
    assert json_resp["data"][user_attribute] == user_value
    if arguments:
        mock_persist_notification.assert_called_once_with(**arguments)
    else:
        mock_persist_notification.assert_not_called()


def test_post_user_attribute_with_updated_by_sends_notification_to_international_from_number(
    admin_request, mocker, sample_user, team_member_mobile_edit_template
):
    updater = create_user(name="Service Manago")
    update_dict = {"mobile_number": "+601117224412", "updated_by": str(updater.id)}
    mocker.patch("app.user.rest.send_notification_to_queue")

    admin_request.post("user.update_user_attribute", user_id=sample_user.id, _data=update_dict)

    notification = Notification.query.first()
    assert notification.reply_to_text == current_app.config["NOTIFY_INTERNATIONAL_SMS_SENDER"]


def test_archive_user(mocker, admin_request, sample_user):
    archive_mock = mocker.patch("app.user.rest.dao_archive_user")

    admin_request.post("user.archive_user", user_id=sample_user.id, _expected_status=204)

    archive_mock.assert_called_once_with(sample_user)


def test_archive_user_when_user_does_not_exist_gives_404(mocker, admin_request, fake_uuid, notify_db_session):
    archive_mock = mocker.patch("app.user.rest.dao_archive_user")

    admin_request.post("user.archive_user", user_id=fake_uuid, _expected_status=404)

    archive_mock.assert_not_called()


def test_archive_user_when_user_cannot_be_archived(mocker, admin_request, sample_user):
    mocker.patch("app.dao.users_dao.user_can_be_archived", return_value=False)

    json_resp = admin_request.post("user.archive_user", user_id=sample_user.id, _expected_status=400)
    msg = "User can’t be removed from a service - check all services have another team member with manage_settings"

    assert json_resp["message"] == msg


def test_fetch_user_by_email(admin_request, notify_db_session):
    user = create_user(email="foo@bar.com")

    create_user(email="foo@bar.com.other_email")
    create_user(email="other_email.foo@bar.com")

    resp = admin_request.post("user.fetch_user_by_email", _data={"email": user.email_address}, _expected_status=200)

    assert resp["data"]["id"] == str(user.id)
    assert resp["data"]["email_address"] == user.email_address


def test_fetch_user_by_email_not_found_returns_404(admin_request, notify_db_session):
    create_user(email="foo@bar.com.other_email")

    resp = admin_request.post("user.fetch_user_by_email", _data={"email": "doesnt@exist.com"}, _expected_status=404)
    assert resp["result"] == "error"
    assert resp["message"] == "No result found"


def test_fetch_user_by_email_without_email_returns_400(admin_request, notify_db_session):
    resp = admin_request.post("user.fetch_user_by_email", _data={}, _expected_status=400)
    assert resp["result"] == "error"
    assert resp["message"] == {"email": ["Missing data for required field."]}


def test_get_user_with_permissions(admin_request, sample_user_service_permission):
    json_resp = admin_request.get(
        "user.get_user",
        user_id=str(sample_user_service_permission.user.id),
    )
    permissions = json_resp["data"]["permissions"]
    assert sample_user_service_permission.permission in permissions[str(sample_user_service_permission.service.id)]


def test_set_user_permissions(admin_request, sample_user, sample_service):
    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data={"permissions": [{"permission": MANAGE_SETTINGS}]},
        _expected_status=204,
    )

    permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_SETTINGS


def test_set_user_permissions_multiple(admin_request, sample_user, sample_service):
    data = {"permissions": [{"permission": MANAGE_SETTINGS}, {"permission": MANAGE_TEMPLATES}]}
    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_SETTINGS
    permission = Permission.query.filter_by(permission=MANAGE_TEMPLATES).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_TEMPLATES


def test_set_user_permissions_remove_old(admin_request, sample_user, sample_service):
    data = {"permissions": [{"permission": MANAGE_SETTINGS}]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    query = Permission.query.filter_by(user=sample_user)
    assert query.count() == 1
    assert query.first().permission == MANAGE_SETTINGS


def test_set_user_folder_permissions(admin_request, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)
    data = {"permissions": [], "folder_permissions": [str(tf1.id), str(tf2.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    assert len(service_user.folders) == 2
    assert tf1 in service_user.folders
    assert tf2 in service_user.folders


def test_set_user_folder_permissions_when_user_does_not_belong_to_service(admin_request, sample_user):
    service = create_service()
    tf1 = create_template_folder(service)
    tf2 = create_template_folder(service)

    data = {"permissions": [], "folder_permissions": [str(tf1.id), str(tf2.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(service.id),
        _data=data,
        _expected_status=404,
    )


def test_set_user_folder_permissions_does_not_affect_permissions_for_other_services(
    admin_request,
    sample_user,
    sample_service,
):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_2 = create_service(sample_user, service_name="other service")
    tf3 = create_template_folder(service_2)

    sample_service_user = dao_get_service_user(sample_user.id, sample_service.id)
    sample_service_user.folders = [tf1]
    dao_update_service_user(sample_service_user)

    service_2_user = dao_get_service_user(sample_user.id, service_2.id)
    service_2_user.folders = [tf3]
    dao_update_service_user(service_2_user)

    data = {"permissions": [], "folder_permissions": [str(tf2.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    assert sample_service_user.folders == [tf2]
    assert service_2_user.folders == [tf3]


def test_update_user_folder_permissions(admin_request, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)
    tf3 = create_template_folder(sample_service)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    data = {"permissions": [], "folder_permissions": [str(tf2.id), str(tf3.id)]}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    assert len(service_user.folders) == 2
    assert tf2 in service_user.folders
    assert tf3 in service_user.folders


def test_remove_user_folder_permissions(admin_request, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    data = {"permissions": [], "folder_permissions": []}

    admin_request.post(
        "user.set_permissions",
        user_id=str(sample_user.id),
        service_id=str(sample_service.id),
        _data=data,
        _expected_status=204,
    )

    assert service_user.folders == []


class TestSetOrganisationUserPermissions:
    def _set_permissions(self, user, organisation, permissions: list[OrganisationUserPermissionTypes]):
        permission_list = [
            OrganisationUserPermissions(organisation=organisation, user=user, permission=p) for p in permissions
        ]
        organisation_user_permissions_dao.set_user_organisation_permission(
            user, organisation, permission_list, _commit=True, replace=True
        )
        new_permissions = OrganisationUserPermissions.query.filter_by(user=user, organisation=organisation).all()
        assert sorted([p.permission for p in new_permissions]) == sorted(permissions)

    def test_requires_admin_auth(self, client, sample_user, sample_organisation, sample_service):
        response = client.post(
            url_for(
                "user.set_organisation_permissions",
                user_id=str(sample_user.id),
                organisation_id=str(sample_organisation.id),
            ),
            data={"permissions": []},
        )
        assert response.status_code == 401

        response = client.post(
            url_for(
                "user.set_organisation_permissions",
                user_id=str(sample_user.id),
                organisation_id=str(sample_organisation.id),
            ),
            data={"permissions": []},
            headers=[create_service_authorization_header(sample_service.id)],
        )
        assert response.status_code == 401

        response = client.post(
            url_for(
                "user.set_organisation_permissions",
                user_id=str(sample_user.id),
                organisation_id=str(sample_organisation.id),
            ),
            json={"permissions": []},
            headers=[create_admin_authorization_header()],
        )
        assert response.status_code == 204

    def test_can_add_permissions(self, admin_request, sample_user, sample_organisation):
        admin_request.post(
            "user.set_organisation_permissions",
            user_id=str(sample_user.id),
            organisation_id=str(sample_organisation.id),
            _data={"permissions": [{"permission": "can_make_services_live"}]},
            _expected_status=204,
        )

        permissions = (
            OrganisationUserPermissions.query.filter_by(user=sample_user, organisation=sample_organisation)
            .order_by("permission")
            .all()
        )
        assert [p.permission for p in permissions] == [OrganisationUserPermissionTypes.can_make_services_live]

    def test_can_remove_permissions(self, admin_request, sample_user, sample_organisation):
        self._set_permissions(
            sample_user, sample_organisation, [OrganisationUserPermissionTypes.can_make_services_live]
        )

        admin_request.post(
            "user.set_organisation_permissions",
            user_id=str(sample_user.id),
            organisation_id=str(sample_organisation.id),
            _data={"permissions": []},
            _expected_status=204,
        )

        permissions = (
            OrganisationUserPermissions.query.filter_by(user=sample_user, organisation=sample_organisation)
            .order_by("permission")
            .all()
        )
        assert [p.permission for p in permissions] == []


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_send_reset_password_link(
    admin_request, sample_user, mocker, password_reset_email_template
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    data = {"email": sample_user.email_address}
    notify_service = password_reset_email_template.service

    admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=204,
    )

    notification = Notification.query.first()
    mocked.assert_called_once_with([str(notification.id)], queue="notify-internal-tasks")
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


@pytest.mark.parametrize(
    "data, expected_url",
    (
        (
            {
                "email": "notify@digital.cabinet-office.gov.uk",
            },
            ("{hostnames.admin}/new-password/"),
        ),
        (
            {
                "email": "notify@digital.cabinet-office.gov.uk",
                "admin_base_url": "https://different.example.com",
            },
            ("https://different.example.com/new-password/"),
        ),
    ),
)
@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_use_provided_base_url(
    admin_request,
    sample_user,
    password_reset_email_template,
    mocker,
    data,
    expected_url,
    hostnames,
):
    mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")

    admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=204,
    )

    assert Notification.query.first().personalisation["url"].startswith(expected_url.format(hostnames=hostnames))


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_reset_password_link_contains_redirect_link_if_present_in_request(
    admin_request, sample_user, mocker, password_reset_email_template
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    data = {"email": sample_user.email_address, "next": "blob"}

    admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=204,
    )

    notification = Notification.query.first()
    assert "?next=blob" in notification.content
    mocked.assert_called_once_with([str(notification.id)], queue="notify-internal-tasks")


def test_send_user_reset_password_should_return_400_when_email_is_missing(admin_request, mocker):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    data = {}

    json_resp = admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=400,
    )
    assert json_resp["message"] == {"email": ["Missing data for required field."]}
    assert mocked.call_count == 0


def test_send_user_reset_password_should_return_400_when_user_doesnot_exist(admin_request, mocker):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    bad_email_address = "bad@email.gov.uk"
    data = {"email": bad_email_address}

    json_resp = admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=404,
    )

    assert json_resp["message"] == "No result found"
    assert mocked.call_count == 0


def test_send_user_reset_password_should_return_400_when_data_is_not_email_address(admin_request, mocker):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    bad_email_address = "bad.email.gov.uk"
    data = {"email": bad_email_address}

    json_resp = admin_request.post(
        "user.send_user_reset_password",
        _data=data,
        _expected_status=400,
    )

    assert json_resp["message"] == {"email": ["Not a valid email address"]}
    assert mocked.call_count == 0


def test_send_already_registered_email(admin_request, sample_user, already_registered_template, mocker):
    data = {"email": sample_user.email_address}
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    notify_service = already_registered_template.service

    admin_request.post(
        "user.send_already_registered_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=204,
    )

    notification = Notification.query.first()
    mocked.assert_called_once_with(([str(notification.id)]), queue="notify-internal-tasks")
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_already_registered_email_returns_400_when_data_is_missing(admin_request, sample_user):
    data = {}

    json_resp = admin_request.post(
        "user.send_already_registered_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=400,
    )
    assert json_resp["message"] == {"email": ["Missing data for required field."]}


def test_send_user_confirm_new_email_returns_204(
    admin_request, sample_user, change_email_confirmation_template, mocker
):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    new_email = "new_address@dig.gov.uk"
    data = {"email": new_email}
    notify_service = change_email_confirmation_template.service

    admin_request.post(
        "user.send_user_confirm_new_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=204,
    )

    notification = Notification.query.first()
    mocked.assert_called_once_with(([str(notification.id)]), queue="notify-internal-tasks")
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_user_confirm_new_email_returns_400_when_email_missing(admin_request, sample_user, mocker):
    mocked = mocker.patch("app.celery.provider_tasks.deliver_email.apply_async")
    data = {}

    json_resp = admin_request.post(
        "user.send_user_confirm_new_email",
        user_id=str(sample_user.id),
        _data=data,
        _expected_status=400,
    )
    assert json_resp["message"] == {"email": ["Missing data for required field."]}
    mocked.assert_not_called()


@freeze_time("2020-02-14T12:00:00")
def test_update_user_password_saves_correctly(admin_request, sample_service):
    sample_user = sample_service.users[0]
    new_password = "1234567890"
    data = {"_password": "1234567890"}

    json_resp = admin_request.post("user.update_password", user_id=str(sample_user.id), _data=data)

    assert json_resp["data"]["password_changed_at"] is not None
    data = {"password": new_password}

    admin_request.post("user.verify_user_password", user_id=str(sample_user.id), _data=data, _expected_status=204)


def test_activate_user(admin_request, sample_user):
    sample_user.state = "pending"

    resp = admin_request.post("user.activate_user", user_id=sample_user.id)

    assert resp["data"]["id"] == str(sample_user.id)
    assert resp["data"]["state"] == "active"
    assert sample_user.state == "active"


def test_activate_user_fails_if_already_active(admin_request, sample_user):
    resp = admin_request.post("user.activate_user", user_id=sample_user.id, _expected_status=400)
    assert resp["message"] == "User already active"
    assert sample_user.state == "active"


def test_update_user_auth_type(admin_request, sample_user):
    assert sample_user.auth_type == "sms_auth"
    resp = admin_request.post(
        "user.update_user_attribute",
        user_id=sample_user.id,
        _data={"auth_type": "email_auth"},
    )

    assert resp["data"]["id"] == str(sample_user.id)
    assert resp["data"]["auth_type"] == "email_auth"


def test_can_set_email_auth_and_remove_mobile_at_same_time(admin_request, sample_user):
    sample_user.auth_type = SMS_AUTH_TYPE

    admin_request.post(
        "user.update_user_attribute",
        user_id=sample_user.id,
        _data={
            "mobile_number": None,
            "auth_type": EMAIL_AUTH_TYPE,
        },
    )

    assert sample_user.mobile_number is None
    assert sample_user.auth_type == EMAIL_AUTH_TYPE


def test_cannot_remove_mobile_if_sms_auth(admin_request, sample_user):
    sample_user.auth_type = SMS_AUTH_TYPE

    json_resp = admin_request.post(
        "user.update_user_attribute", user_id=sample_user.id, _data={"mobile_number": None}, _expected_status=400
    )

    assert json_resp["message"] == "Mobile number must be set if auth_type is set to sms_auth"


def test_can_remove_mobile_if_email_auth(admin_request, sample_user):
    sample_user.auth_type = EMAIL_AUTH_TYPE

    admin_request.post(
        "user.update_user_attribute",
        user_id=sample_user.id,
        _data={"mobile_number": None},
    )

    assert sample_user.mobile_number is None


def test_cannot_update_user_with_mobile_number_as_empty_string(admin_request, sample_user):
    sample_user.auth_type = EMAIL_AUTH_TYPE

    resp = admin_request.post(
        "user.update_user_attribute", user_id=sample_user.id, _data={"mobile_number": ""}, _expected_status=400
    )
    assert resp["message"]["mobile_number"] == ["Invalid phone number: Not enough digits"]


def test_cannot_update_user_password_using_attributes_method(admin_request, sample_user):
    resp = admin_request.post(
        "user.update_user_attribute", user_id=sample_user.id, _data={"password": "foo"}, _expected_status=400
    )
    assert resp == {"message": {"_schema": ["Unknown field name password"]}, "result": "error"}


def test_get_orgs_and_services_nests_services(admin_request, sample_user):
    org1 = create_organisation(name="org1")
    org2 = create_organisation(name="org2")
    service1 = create_service(service_name="service1")
    service2 = create_service(service_name="service2")
    service3 = create_service(service_name="service3")

    org1.services = [service1, service2]
    org2.services = []

    sample_user.organisations = [org1, org2]
    sample_user.services = [service1, service2, service3]

    resp = admin_request.get("user.get_organisations_and_services_for_user", user_id=sample_user.id)

    assert set(resp.keys()) == {
        "organisations",
        "services",
    }
    assert resp["organisations"] == [
        {
            "name": org1.name,
            "id": str(org1.id),
            "count_of_live_services": 2,
        },
        {
            "name": org2.name,
            "id": str(org2.id),
            "count_of_live_services": 0,
        },
    ]
    assert resp["services"] == [
        {
            "name": service1.name,
            "id": str(service1.id),
            "restricted": False,
            "organisation": str(org1.id),
        },
        {
            "name": service2.name,
            "id": str(service2.id),
            "restricted": False,
            "organisation": str(org1.id),
        },
        {
            "name": service3.name,
            "id": str(service3.id),
            "restricted": False,
            "organisation": None,
        },
    ]


def test_get_orgs_and_services_only_returns_active(admin_request, sample_user):
    org1 = create_organisation(name="org1", active=True)
    org2 = create_organisation(name="org2", active=False)

    # in an active org
    service1 = create_service(service_name="service1", active=True)
    service2 = create_service(service_name="service2", active=False)
    # active but in an inactive org
    service3 = create_service(service_name="service3", active=True)
    # not in an org
    service4 = create_service(service_name="service4", active=True)
    service5 = create_service(service_name="service5", active=False)

    org1.services = [service1, service2]
    org2.services = [service3]

    sample_user.organisations = [org1, org2]
    sample_user.services = [service1, service2, service3, service4, service5]

    resp = admin_request.get("user.get_organisations_and_services_for_user", user_id=sample_user.id)

    assert set(resp.keys()) == {
        "organisations",
        "services",
    }
    assert resp["organisations"] == [
        {
            "name": org1.name,
            "id": str(org1.id),
            "count_of_live_services": 1,
        }
    ]
    assert resp["services"] == [
        {"name": service1.name, "id": str(service1.id), "restricted": False, "organisation": str(org1.id)},
        {"name": service3.name, "id": str(service3.id), "restricted": False, "organisation": str(org2.id)},
        {
            "name": service4.name,
            "id": str(service4.id),
            "restricted": False,
            "organisation": None,
        },
    ]


def test_get_orgs_and_services_only_shows_users_orgs_and_services(admin_request, sample_user):
    other_user = create_user(email="other@user.com")

    org1 = create_organisation(name="org1")
    org2 = create_organisation(name="org2")
    service1 = create_service(service_name="service1")
    service2 = create_service(service_name="service2")

    org1.services = [service1]

    sample_user.organisations = [org2]
    sample_user.services = [service1]

    other_user.organisations = [org1, org2]
    other_user.services = [service1, service2]

    resp = admin_request.get("user.get_organisations_and_services_for_user", user_id=sample_user.id)

    assert set(resp.keys()) == {
        "organisations",
        "services",
    }
    assert resp["organisations"] == [
        {
            "name": org2.name,
            "id": str(org2.id),
            "count_of_live_services": 0,
        }
    ]
    # 'services' always returns the org_id no matter whether the user
    # belongs to that org or not
    assert resp["services"] == [
        {
            "name": service1.name,
            "id": str(service1.id),
            "restricted": False,
            "organisation": str(org1.id),
        }
    ]


def test_find_users_by_email_finds_user_by_partial_email(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    create_user(email="me.ignorra@foo.com")
    data = {"email": "findel"}

    users = admin_request.post(
        "user.find_users_by_email",
        _data=data,
    )

    assert len(users["data"]) == 1
    assert users["data"][0]["email_address"] == "findel.mestro@foo.com"


def test_find_users_by_email_finds_user_by_full_email(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    create_user(email="me.ignorra@foo.com")
    data = {"email": "findel.mestro@foo.com"}

    users = admin_request.post(
        "user.find_users_by_email",
        _data=data,
    )

    assert len(users["data"]) == 1
    assert users["data"][0]["email_address"] == "findel.mestro@foo.com"


def test_find_users_by_email_handles_no_results(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    create_user(email="me.ignorra@foo.com")
    data = {"email": "rogue"}

    users = admin_request.post(
        "user.find_users_by_email",
        _data=data,
    )

    assert users["data"] == []


def test_search_for_users_by_email_handles_incorrect_data_format(notify_db_session, admin_request):
    create_user(email="findel.mestro@foo.com")
    data = {"email": 1}

    json = admin_request.post("user.find_users_by_email", _data=data, _expected_status=400)

    assert json["message"] == {"email": ["Not a valid string."]}


@pytest.mark.parametrize(
    "number, expected_reply_to",
    [
        ("1-403-123-4567", "notify_international_sender"),
        ("27 123 4569 2312", "notify_international_sender"),
        ("30 123 4567 7890", "Notify"),
        ("+20 123 4567 7890", "Notify"),
    ],
)
def test_get_sms_reply_to_for_notify_service(team_member_mobile_edit_template, number, expected_reply_to):
    # need to import locally to avoid db session errors,
    # if this import is with the other imports at the top of the file
    # the imports happen in the wrong order and you'll see "dummy session" errors
    from app.user.rest import get_sms_reply_to_for_notify_service

    reply_to = get_sms_reply_to_for_notify_service(number, team_member_mobile_edit_template)
    assert (
        reply_to == current_app.config["NOTIFY_INTERNATIONAL_SMS_SENDER"]
        if expected_reply_to == "notify_international_sender"
        else current_app.config["FROM_NUMBER"]
    )


@freeze_time("2020-01-01 11:00")
def test_complete_login_after_webauthn_authentication_attempt_resets_login_if_successful(admin_request, sample_user):
    sample_user.failed_login_count = 1

    assert sample_user.current_session_id is None
    assert sample_user.logged_in_at is None

    webauthn_credential = create_webauthn_credential(sample_user)
    assert webauthn_credential.logged_in_at is None

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": True},
        _expected_status=204,
    )

    assert sample_user.current_session_id is not None
    assert sample_user.failed_login_count == 0
    assert sample_user.logged_in_at == datetime(2020, 1, 1, 11, 0)
    assert webauthn_credential.logged_in_at is None


@freeze_time("2020-01-01 11:00")
def test_complete_login_after_webauthn_authentication_attempt_updates_logged_in_at_for_supplied_webauthn_credential(
    admin_request, sample_user
):
    assert sample_user.current_session_id is None
    assert sample_user.logged_in_at is None

    webauthn_credential = create_webauthn_credential(sample_user)
    assert webauthn_credential.logged_in_at is None

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": True, "webauthn_credential_id": str(webauthn_credential.id)},
        _expected_status=204,
    )

    assert sample_user.logged_in_at == datetime(2020, 1, 1, 11, 0)
    assert webauthn_credential.logged_in_at == datetime(2020, 1, 1, 11, 0)


def test_complete_login_after_webauthn_authentication_attempt_returns_204_when_not_successful(
    admin_request, sample_user
):
    # when unsuccessful this endpoint is used to bump the failed count. the endpoint still worked
    # properly so should return 204 (no content).
    sample_user.failed_login_count = 1

    assert sample_user.current_session_id is None
    assert sample_user.logged_in_at is None

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": False},
        _expected_status=204,
    )

    assert sample_user.current_session_id is None
    assert sample_user.failed_login_count == 2
    assert sample_user.logged_in_at is None


def test_complete_login_after_webauthn_authentication_attempt_raises_403_if_max_login_count_exceeded(
    admin_request, sample_user
):
    # when unsuccessful this endpoint is used to bump the failed count. the endpoint still worked
    # properly so should return 204 (no content).
    sample_user.failed_login_count = 10

    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=sample_user.id,
        _data={"successful": True},
        _expected_status=403,
    )

    assert sample_user.current_session_id is None
    assert sample_user.failed_login_count == 10
    assert sample_user.logged_in_at is None


def test_complete_login_after_webauthn_authentication_attempt_raises_400_if_schema_invalid(admin_request):
    admin_request.post(
        "user.complete_login_after_webauthn_authentication_attempt",
        user_id=uuid.uuid4(),
        _data={"successful": "True"},
        _expected_status=400,
    )
