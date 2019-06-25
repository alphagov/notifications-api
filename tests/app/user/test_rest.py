import json
import pytest
import mock
from uuid import UUID

from flask import url_for
from freezegun import freeze_time

from app.models import (
    User,
    Permission,
    MANAGE_SETTINGS,
    MANAGE_TEMPLATES,
    Notification,
    SMS_AUTH_TYPE,
    EMAIL_AUTH_TYPE
)
from app.dao.permissions_dao import default_service_permissions
from app.dao.service_user_dao import dao_get_service_user, dao_update_service_user
from tests import create_authorization_header
from tests.app.db import create_service, create_template_folder, create_organisation, create_user


def test_get_user_list(admin_request, sample_service):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    json_resp = admin_request.get('user.get_user')

    # it may have the notify user in the DB still :weary:
    assert len(json_resp['data']) >= 1
    sample_user = sample_service.users[0]
    expected_permissions = default_service_permissions
    fetched = next(x for x in json_resp['data'] if x['id'] == str(sample_user.id))

    assert sample_user.name == fetched['name']
    assert sample_user.mobile_number == fetched['mobile_number']
    assert sample_user.email_address == fetched['email_address']
    assert sample_user.state == fetched['state']
    assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_get_user(admin_request, sample_service, sample_organisation):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    sample_user = sample_service.users[0]
    sample_user.organisations = [sample_organisation]
    json_resp = admin_request.get(
        'user.get_user',
        user_id=sample_user.id
    )

    expected_permissions = default_service_permissions
    fetched = json_resp['data']

    assert fetched['id'] == str(sample_user.id)
    assert fetched['name'] == sample_user.name
    assert fetched['mobile_number'] == sample_user.mobile_number
    assert fetched['email_address'] == sample_user.email_address
    assert fetched['state'] == sample_user.state
    assert fetched['auth_type'] == SMS_AUTH_TYPE
    assert fetched['permissions'].keys() == {str(sample_service.id)}
    assert fetched['services'] == [str(sample_service.id)]
    assert fetched['organisations'] == [str(sample_organisation.id)]
    assert sorted(fetched['permissions'][str(sample_service.id)]) == sorted(expected_permissions)


def test_get_user_doesnt_return_inactive_services_and_orgs(admin_request, sample_service, sample_organisation):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    sample_service.active = False
    sample_organisation.active = False

    sample_user = sample_service.users[0]
    sample_user.organisations = [sample_organisation]

    json_resp = admin_request.get(
        'user.get_user',
        user_id=sample_user.id
    )

    fetched = json_resp['data']

    assert fetched['id'] == str(sample_user.id)
    assert fetched['services'] == []
    assert fetched['organisations'] == []
    assert fetched['permissions'] == {}


def test_post_user(client, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' to create a user.
    """
    assert User.query.count() == 0
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {},
        "auth_type": EMAIL_AUTH_TYPE
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.post(
        url_for('user.create_user'),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 201
    user = User.query.filter_by(email_address='user@digital.cabinet-office.gov.uk').first()
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data']['email_address'] == user.email_address
    assert json_resp['data']['id'] == str(user.id)
    assert user.auth_type == EMAIL_AUTH_TYPE


def test_post_user_without_auth_type(admin_request, notify_db_session):
    assert User.query.count() == 0
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": "+447700900986",
        "permissions": {},
    }

    json_resp = admin_request.post('user.create_user', _data=data, _expected_status=201)

    user = User.query.filter_by(email_address='user@digital.cabinet-office.gov.uk').first()
    assert json_resp['data']['id'] == str(user.id)
    assert user.auth_type == SMS_AUTH_TYPE


def test_post_user_missing_attribute_email(client, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute email.
    """
    assert User.query.count() == 0
    data = {
        "name": "Test User",
        "password": "password",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {}
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.post(
        url_for('user.create_user'),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 400
    assert User.query.count() == 0
    json_resp = json.loads(resp.get_data(as_text=True))
    assert {'email_address': ['Missing data for required field.']} == json_resp['message']


def test_create_user_missing_attribute_password(client, notify_db, notify_db_session):
    """
    Tests POST endpoint '/' missing attribute password.
    """
    assert User.query.count() == 0
    data = {
        "name": "Test User",
        "email_address": "user@digital.cabinet-office.gov.uk",
        "mobile_number": "+447700900986",
        "logged_in_at": None,
        "state": "active",
        "failed_login_count": 0,
        "permissions": {}
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.post(
        url_for('user.create_user'),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 400
    assert User.query.count() == 0
    json_resp = json.loads(resp.get_data(as_text=True))
    assert {'password': ['Missing data for required field.']} == json_resp['message']


def test_can_create_user_with_email_auth_and_no_mobile(admin_request, notify_db_session):
    data = {
        'name': 'Test User',
        'email_address': 'user@digital.cabinet-office.gov.uk',
        'password': 'password',
        'mobile_number': None,
        'auth_type': EMAIL_AUTH_TYPE
    }

    json_resp = admin_request.post('user.create_user', _data=data, _expected_status=201)

    assert json_resp['data']['auth_type'] == EMAIL_AUTH_TYPE
    assert json_resp['data']['mobile_number'] is None


def test_cannot_create_user_with_sms_auth_and_no_mobile(admin_request, notify_db_session):
    data = {
        'name': 'Test User',
        'email_address': 'user@digital.cabinet-office.gov.uk',
        'password': 'password',
        'mobile_number': None,
        'auth_type': SMS_AUTH_TYPE
    }

    json_resp = admin_request.post('user.create_user', _data=data, _expected_status=400)

    assert json_resp['message'] == 'Mobile number must be set if auth_type is set to sms_auth'


def test_cannot_create_user_with_empty_strings(admin_request, notify_db_session):
    data = {
        'name': '',
        'email_address': '',
        'password': 'password',
        'mobile_number': '',
        'auth_type': EMAIL_AUTH_TYPE
    }
    resp = admin_request.post(
        'user.create_user',
        _data=data,
        _expected_status=400
    )
    assert resp['message'] == {
        'email_address': ['Not a valid email address'],
        'mobile_number': ['Invalid phone number: Not enough digits'],
        'name': ['Invalid name']
    }


@pytest.mark.parametrize('user_attribute, user_value', [
    ('name', 'New User'),
    ('email_address', 'newuser@mail.com'),
    ('mobile_number', '+4407700900460')
])
def test_post_user_attribute(client, sample_user, user_attribute, user_value):
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {
        user_attribute: user_value
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]

    resp = client.post(
        url_for('user.update_user_attribute', user_id=sample_user.id),
        data=json.dumps(update_dict),
        headers=headers)

    assert resp.status_code == 200
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data'][user_attribute] == user_value


@pytest.mark.parametrize('user_attribute, user_value, arguments', [
    ('name', 'New User', None),
    ('email_address', 'newuser@mail.com', dict(
        api_key_id=None, key_type='normal', notification_type='email',
        personalisation={
            'name': 'Test User', 'servicemanagername': 'Service Manago', 'email address': 'newuser@mail.com'
        },
        recipient='newuser@mail.com', reply_to_text='notify@gov.uk',
        service=mock.ANY,
        template_id=UUID('c73f1d71-4049-46d5-a647-d013bdeca3f0'), template_version=1
    )),
    ('mobile_number', '+4407700900460', dict(
        api_key_id=None, key_type='normal', notification_type='sms',
        personalisation={
            'name': 'Test User', 'servicemanagername': 'Service Manago',
            'email address': 'notify@digital.cabinet-office.gov.uk'
        },
        recipient='+4407700900460', reply_to_text='testing', service=mock.ANY,
        template_id=UUID('8a31520f-4751-4789-8ea1-fe54496725eb'), template_version=1
    ))
])
def test_post_user_attribute_with_updated_by(
    client, mocker, sample_user, user_attribute,
    user_value, arguments, team_member_email_edit_template, team_member_mobile_edit_template
):
    updater = create_user(name="Service Manago", email="notify_manago@digital.cabinet-office.gov.uk")
    assert getattr(sample_user, user_attribute) != user_value
    update_dict = {
        user_attribute: user_value,
        'updated_by': str(updater.id)
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    mock_persist_notification = mocker.patch('app.user.rest.persist_notification')
    mocker.patch('app.user.rest.send_notification_to_queue')
    resp = client.post(
        url_for('user.update_user_attribute', user_id=sample_user.id),
        data=json.dumps(update_dict),
        headers=headers)

    assert resp.status_code == 200, resp.get_data(as_text=True)
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data'][user_attribute] == user_value
    if arguments:
        mock_persist_notification.assert_called_once_with(**arguments)
    else:
        mock_persist_notification.assert_not_called()


def test_archive_user(mocker, client, sample_user):
    archive_mock = mocker.patch('app.user.rest.dao_archive_user')

    response = client.post(
        url_for('user.archive_user', user_id=sample_user.id),
        headers=[create_authorization_header()]
    )

    assert response.status_code == 204
    archive_mock.assert_called_once_with(sample_user)


def test_archive_user_when_user_does_not_exist_gives_404(mocker, client, fake_uuid, notify_db_session):
    archive_mock = mocker.patch('app.user.rest.dao_archive_user')

    response = client.post(
        url_for('user.archive_user', user_id=fake_uuid),
        headers=[create_authorization_header()]
    )

    assert response.status_code == 404
    archive_mock.assert_not_called()


def test_archive_user_when_user_cannot_be_archived(mocker, client, sample_user):
    mocker.patch('app.dao.users_dao.user_can_be_archived', return_value=False)

    response = client.post(
        url_for('user.archive_user', user_id=sample_user.id),
        headers=[create_authorization_header()]
    )
    json_resp = json.loads(response.get_data(as_text=True))

    msg = "User can’t be removed from a service - check all services have another team member with manage_settings"

    assert response.status_code == 400
    assert json_resp['message'] == msg


def test_get_user_by_email(client, sample_service):
    sample_user = sample_service.users[0]
    header = create_authorization_header()
    url = url_for('user.get_by_email', email=sample_user.email_address)
    resp = client.get(url, headers=[header])
    assert resp.status_code == 200

    json_resp = json.loads(resp.get_data(as_text=True))
    expected_permissions = default_service_permissions
    fetched = json_resp['data']

    assert str(sample_user.id) == fetched['id']
    assert sample_user.name == fetched['name']
    assert sample_user.mobile_number == fetched['mobile_number']
    assert sample_user.email_address == fetched['email_address']
    assert sample_user.state == fetched['state']
    assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


def test_get_user_by_email_not_found_returns_404(client, sample_user):
    header = create_authorization_header()
    url = url_for('user.get_by_email', email='no_user@digital.gov.uk')
    resp = client.get(url, headers=[header])
    assert resp.status_code == 404
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'No result found'


def test_get_user_by_email_bad_url_returns_404(client, sample_user):
    header = create_authorization_header()
    url = '/user/email'
    resp = client.get(url, headers=[header])
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'Invalid request. Email query string param required'


def test_get_user_with_permissions(client, sample_user_service_permission):
    header = create_authorization_header()
    response = client.get(url_for('user.get_user', user_id=str(sample_user_service_permission.user.id)),
                          headers=[header])
    assert response.status_code == 200
    permissions = json.loads(response.get_data(as_text=True))['data']['permissions']
    assert sample_user_service_permission.permission in permissions[str(sample_user_service_permission.service.id)]


def test_set_user_permissions(client, sample_user, sample_service):
    data = json.dumps({'permissions': [{'permission': MANAGE_SETTINGS}]})
    header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), header]
    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=headers,
        data=data)

    assert response.status_code == 204
    permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_SETTINGS


def test_set_user_permissions_multiple(client, sample_user, sample_service):
    data = json.dumps({'permissions': [{'permission': MANAGE_SETTINGS}, {'permission': MANAGE_TEMPLATES}]})
    header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), header]
    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=headers,
        data=data)

    assert response.status_code == 204
    permission = Permission.query.filter_by(permission=MANAGE_SETTINGS).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_SETTINGS
    permission = Permission.query.filter_by(permission=MANAGE_TEMPLATES).first()
    assert permission.user == sample_user
    assert permission.service == sample_service
    assert permission.permission == MANAGE_TEMPLATES


def test_set_user_permissions_remove_old(client, sample_user, sample_service):
    data = json.dumps({'permissions': [{'permission': MANAGE_SETTINGS}]})
    header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), header]
    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=headers,
        data=data)

    assert response.status_code == 204
    query = Permission.query.filter_by(user=sample_user)
    assert query.count() == 1
    assert query.first().permission == MANAGE_SETTINGS


def test_set_user_folder_permissions(client, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)
    data = json.dumps({'permissions': [], 'folder_permissions': [str(tf1.id), str(tf2.id)]})

    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=data)

    assert response.status_code == 204

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    assert len(service_user.folders) == 2
    assert tf1 in service_user.folders
    assert tf2 in service_user.folders


def test_set_user_folder_permissions_when_user_does_not_belong_to_service(client, sample_user):
    service = create_service()
    tf1 = create_template_folder(service)
    tf2 = create_template_folder(service)

    data = json.dumps({'permissions': [], 'folder_permissions': [str(tf1.id), str(tf2.id)]})

    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=data)

    assert response.status_code == 404


def test_set_user_folder_permissions_does_not_affect_permissions_for_other_services(
    client,
    sample_user,
    sample_service,
):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_2 = create_service(sample_user, service_name='other service')
    tf3 = create_template_folder(service_2)

    sample_service_user = dao_get_service_user(sample_user.id, sample_service.id)
    sample_service_user.folders = [tf1]
    dao_update_service_user(sample_service_user)

    service_2_user = dao_get_service_user(sample_user.id, service_2.id)
    service_2_user.folders = [tf3]
    dao_update_service_user(service_2_user)

    data = json.dumps({'permissions': [], 'folder_permissions': [str(tf2.id)]})

    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=data)

    assert response.status_code == 204

    assert sample_service_user.folders == [tf2]
    assert service_2_user.folders == [tf3]


def test_update_user_folder_permissions(client, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)
    tf3 = create_template_folder(sample_service)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    data = json.dumps({'permissions': [], 'folder_permissions': [str(tf2.id), str(tf3.id)]})

    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=data)

    assert response.status_code == 204
    assert len(service_user.folders) == 2
    assert tf2 in service_user.folders
    assert tf3 in service_user.folders


def test_remove_user_folder_permissions(client, sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    data = json.dumps({'permissions': [], 'folder_permissions': []})

    response = client.post(
        url_for(
            'user.set_permissions',
            user_id=str(sample_user.id),
            service_id=str(sample_service.id)),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=data)

    assert response.status_code == 204
    assert service_user.folders == []


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_send_reset_password_link(client,
                                                                  sample_user,
                                                                  mocker,
                                                                  password_reset_email_template):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = json.dumps({'email': sample_user.email_address})
    auth_header = create_authorization_header()
    notify_service = password_reset_email_template.service
    resp = client.post(
        url_for('user.send_user_reset_password'),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 204
    notification = Notification.query.first()
    mocked.assert_called_once_with([str(notification.id)], queue="notify-internal-tasks")
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_user_reset_password_should_return_400_when_email_is_missing(client, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = json.dumps({})
    auth_header = create_authorization_header()

    resp = client.post(
        url_for('user.send_user_reset_password'),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 400
    assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Missing data for required field.']}
    assert mocked.call_count == 0


def test_send_user_reset_password_should_return_400_when_user_doesnot_exist(client, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    bad_email_address = 'bad@email.gov.uk'
    data = json.dumps({'email': bad_email_address})
    auth_header = create_authorization_header()

    resp = client.post(
        url_for('user.send_user_reset_password'),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 404
    assert json.loads(resp.get_data(as_text=True))['message'] == 'No result found'
    assert mocked.call_count == 0


def test_send_user_reset_password_should_return_400_when_data_is_not_email_address(client, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    bad_email_address = 'bad.email.gov.uk'
    data = json.dumps({'email': bad_email_address})
    auth_header = create_authorization_header()

    resp = client.post(
        url_for('user.send_user_reset_password'),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 400
    assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Not a valid email address']}
    assert mocked.call_count == 0


def test_send_already_registered_email(client, sample_user, already_registered_template, mocker):
    data = json.dumps({'email': sample_user.email_address})
    auth_header = create_authorization_header()
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    notify_service = already_registered_template.service

    resp = client.post(
        url_for('user.send_already_registered_email', user_id=str(sample_user.id)),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204

    notification = Notification.query.first()
    mocked.assert_called_once_with(([str(notification.id)]), queue="notify-internal-tasks")
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_already_registered_email_returns_400_when_data_is_missing(client, sample_user):
    data = json.dumps({})
    auth_header = create_authorization_header()

    resp = client.post(
        url_for('user.send_already_registered_email', user_id=str(sample_user.id)),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Missing data for required field.']}


def test_send_user_confirm_new_email_returns_204(client, sample_user, change_email_confirmation_template, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    new_email = 'new_address@dig.gov.uk'
    data = json.dumps({'email': new_email})
    auth_header = create_authorization_header()
    notify_service = change_email_confirmation_template.service

    resp = client.post(url_for('user.send_user_confirm_new_email', user_id=str(sample_user.id)),
                       data=data,
                       headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204
    notification = Notification.query.first()
    mocked.assert_called_once_with(
        ([str(notification.id)]),
        queue="notify-internal-tasks")
    assert notification.reply_to_text == notify_service.get_default_reply_to_email_address()


def test_send_user_confirm_new_email_returns_400_when_email_missing(client, sample_user, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = json.dumps({})
    auth_header = create_authorization_header()
    resp = client.post(url_for('user.send_user_confirm_new_email', user_id=str(sample_user.id)),
                       data=data,
                       headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 400
    assert json.loads(resp.get_data(as_text=True))['message'] == {'email': ['Missing data for required field.']}
    mocked.assert_not_called()


def test_update_user_password_saves_correctly(client, sample_service):
    sample_user = sample_service.users[0]
    new_password = '1234567890'
    data = {
        '_password': new_password
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.post(
        url_for('user.update_password', user_id=sample_user.id),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 200

    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data']['password_changed_at'] is not None
    data = {'password': new_password}
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.post(
        url_for('user.verify_user_password', user_id=str(sample_user.id)),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 204


def test_activate_user(admin_request, sample_user):
    sample_user.state = 'pending'

    resp = admin_request.post('user.activate_user', user_id=sample_user.id)

    assert resp['data']['id'] == str(sample_user.id)
    assert resp['data']['state'] == 'active'
    assert sample_user.state == 'active'


def test_activate_user_fails_if_already_active(admin_request, sample_user):
    resp = admin_request.post('user.activate_user', user_id=sample_user.id, _expected_status=400)
    assert resp['message'] == 'User already active'
    assert sample_user.state == 'active'


def test_update_user_auth_type(admin_request, sample_user):
    assert sample_user.auth_type == 'sms_auth'
    resp = admin_request.post(
        'user.update_user_attribute',
        user_id=sample_user.id,
        _data={'auth_type': 'email_auth'},
    )

    assert resp['data']['id'] == str(sample_user.id)
    assert resp['data']['auth_type'] == 'email_auth'


def test_can_set_email_auth_and_remove_mobile_at_same_time(admin_request, sample_user):
    sample_user.auth_type = SMS_AUTH_TYPE

    admin_request.post(
        'user.update_user_attribute',
        user_id=sample_user.id,
        _data={
            'mobile_number': None,
            'auth_type': EMAIL_AUTH_TYPE,
        }
    )

    assert sample_user.mobile_number is None
    assert sample_user.auth_type == EMAIL_AUTH_TYPE


def test_cannot_remove_mobile_if_sms_auth(admin_request, sample_user):
    sample_user.auth_type = SMS_AUTH_TYPE

    json_resp = admin_request.post(
        'user.update_user_attribute',
        user_id=sample_user.id,
        _data={'mobile_number': None},
        _expected_status=400
    )

    assert json_resp['message'] == 'Mobile number must be set if auth_type is set to sms_auth'


def test_can_remove_mobile_if_email_auth(admin_request, sample_user):
    sample_user.auth_type = EMAIL_AUTH_TYPE

    admin_request.post(
        'user.update_user_attribute',
        user_id=sample_user.id,
        _data={'mobile_number': None},
    )

    assert sample_user.mobile_number is None


def test_cannot_update_user_with_mobile_number_as_empty_string(admin_request, sample_user):
    sample_user.auth_type = EMAIL_AUTH_TYPE

    resp = admin_request.post(
        'user.update_user_attribute',
        user_id=sample_user.id,
        _data={'mobile_number': ''},
        _expected_status=400
    )
    assert resp['message']['mobile_number'] == ['Invalid phone number: Not enough digits']


def test_cannot_update_user_password_using_attributes_method(admin_request, sample_user):
    resp = admin_request.post(
        'user.update_user_attribute',
        user_id=sample_user.id,
        _data={'password': 'foo'},
        _expected_status=400
    )
    assert resp['message']['_schema'] == ['Unknown field name password']


def test_get_orgs_and_services_nests_services(admin_request, sample_user):
    org1 = create_organisation(name='org1')
    org2 = create_organisation(name='org2')
    service1 = create_service(service_name='service1')
    service2 = create_service(service_name='service2')
    service3 = create_service(service_name='service3')

    org1.services = [service1, service2]
    org2.services = []

    sample_user.organisations = [org1, org2]
    sample_user.services = [service1, service2, service3]

    resp = admin_request.get('user.get_organisations_and_services_for_user', user_id=sample_user.id)

    assert set(resp.keys()) == {
        'organisations',
        'services_without_organisations',
        'services',
    }
    assert resp['organisations'] == [
        {
            'name': org1.name,
            'id': str(org1.id),
            'services': [
                {
                    'name': service1.name,
                    'id': str(service1.id),
                    'restricted': False,
                },
                {
                    'name': service2.name,
                    'id': str(service2.id),
                    'restricted': False,
                }
            ],
            'count_of_live_services': 2,
        },
        {
            'name': org2.name,
            'id': str(org2.id),
            'services': [],
            'count_of_live_services': 0,
        },
    ]
    assert resp['services_without_organisations'] == [
        {
            'name': service3.name,
            'id': str(service3.id),
            'restricted': False,
        }
    ]
    assert resp['services'] == [
        {
            'name': service1.name,
            'id': str(service1.id),
            'restricted': False,
            'organisation': str(org1.id),
        },
        {
            'name': service2.name,
            'id': str(service2.id),
            'restricted': False,
            'organisation': str(org1.id),
        },
        {
            'name': service3.name,
            'id': str(service3.id),
            'restricted': False,
            'organisation': None,
        },
    ]


def test_get_orgs_and_services_only_returns_active(admin_request, sample_user):
    org1 = create_organisation(name='org1', active=True)
    org2 = create_organisation(name='org2', active=False)

    # in an active org
    service1 = create_service(service_name='service1', active=True)
    service2 = create_service(service_name='service2', active=False)
    # active but in an inactive org
    service3 = create_service(service_name='service3', active=True)
    # not in an org
    service4 = create_service(service_name='service4', active=True)
    service5 = create_service(service_name='service5', active=False)

    org1.services = [service1, service2]
    org2.services = [service3]

    sample_user.organisations = [org1, org2]
    sample_user.services = [service1, service2, service3, service4, service5]

    resp = admin_request.get('user.get_organisations_and_services_for_user', user_id=sample_user.id)

    assert set(resp.keys()) == {
        'organisations',
        'services_without_organisations',
        'services',
    }
    assert resp['organisations'] == [
        {
            'name': org1.name,
            'id': str(org1.id),
            'services': [
                {
                    'name': service1.name,
                    'id': str(service1.id),
                    'restricted': False,
                }
            ],
            'count_of_live_services': 1,
        }
    ]
    assert resp['services_without_organisations'] == [
        {
            'name': service4.name,
            'id': str(service4.id),
            'restricted': False,
        }
    ]
    assert resp['services'] == [
        {
            'name': service1.name,
            'id': str(service1.id),
            'restricted': False,
            'organisation': str(org1.id)
        },
        {
            'name': service3.name,
            'id': str(service3.id),
            'restricted': False,
            'organisation': str(org2.id)
        },
        {
            'name': service4.name,
            'id': str(service4.id),
            'restricted': False,
            'organisation': None,
        },
    ]


def test_get_orgs_and_services_only_shows_users_orgs_and_services(admin_request, sample_user):
    other_user = create_user(email='other@user.com')

    org1 = create_organisation(name='org1')
    org2 = create_organisation(name='org2')
    service1 = create_service(service_name='service1')
    service2 = create_service(service_name='service2')

    org1.services = [service1]

    sample_user.organisations = [org2]
    sample_user.services = [service1]

    other_user.organisations = [org1, org2]
    other_user.services = [service1, service2]

    resp = admin_request.get('user.get_organisations_and_services_for_user', user_id=sample_user.id)

    assert set(resp.keys()) == {
        'organisations',
        'services_without_organisations',
        'services',
    }
    assert resp['organisations'] == [
        {
            'name': org2.name,
            'id': str(org2.id),
            'services': [],
            'count_of_live_services': 0,
        }
    ]
    # service1 belongs to org1, but the user doesn't know about org1
    assert resp['services_without_organisations'] == [
        {
            'name': service1.name,
            'id': str(service1.id),
            'restricted': False,
        }
    ]
    # 'services' always returns the org_id no matter whether the user
    # belongs to that org or not
    assert resp['services'] == [
        {
            'name': service1.name,
            'id': str(service1.id),
            'restricted': False,
            'organisation': str(org1.id),
        }
    ]


def test_find_users_by_email_finds_user_by_partial_email(notify_db, client):
    create_user(email='findel.mestro@foo.com')
    create_user(email='me.ignorra@foo.com')
    data = json.dumps({"email": "findel"})
    auth_header = create_authorization_header()

    response = client.post(
        url_for("user.find_users_by_email"),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    users = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert len(users['data']) == 1
    assert users['data'][0]['email_address'] == 'findel.mestro@foo.com'


def test_find_users_by_email_finds_user_by_full_email(notify_db, client):
    create_user(email='findel.mestro@foo.com')
    create_user(email='me.ignorra@foo.com')
    data = json.dumps({"email": "findel.mestro@foo.com"})
    auth_header = create_authorization_header()

    response = client.post(
        url_for("user.find_users_by_email"),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    users = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert len(users['data']) == 1
    assert users['data'][0]['email_address'] == 'findel.mestro@foo.com'


def test_find_users_by_email_handles_no_results(notify_db, client):
    create_user(email='findel.mestro@foo.com')
    create_user(email='me.ignorra@foo.com')
    data = json.dumps({"email": "rogue"})
    auth_header = create_authorization_header()

    response = client.post(
        url_for("user.find_users_by_email"),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    users = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert users['data'] == []


def test_search_for_users_by_email_handles_incorrect_data_format(notify_db, client):
    create_user(email='findel.mestro@foo.com')
    data = json.dumps({"email": 1})
    auth_header = create_authorization_header()

    response = client.post(
        url_for("user.find_users_by_email"),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    assert response.status_code == 400
    assert json.loads(response.get_data(as_text=True))['message'] == {'email': ['Not a valid string.']}
