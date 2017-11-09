import json
import pytest

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
from tests import create_authorization_header


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


def test_get_user(client, sample_service):
    """
    Tests GET endpoint '/<user_id>' to retrieve a single service.
    """
    sample_user = sample_service.users[0]
    header = create_authorization_header()
    resp = client.get(url_for('user.get_user',
                              user_id=sample_user.id),
                      headers=[header])
    assert resp.status_code == 200
    json_resp = json.loads(resp.get_data(as_text=True))

    expected_permissions = default_service_permissions
    fetched = json_resp['data']

    assert str(sample_user.id) == fetched['id']
    assert sample_user.name == fetched['name']
    assert sample_user.mobile_number == fetched['mobile_number']
    assert sample_user.email_address == fetched['email_address']
    assert sample_user.state == fetched['state']
    assert fetched['auth_type'] == SMS_AUTH_TYPE
    assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])


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
    data = json.dumps([{'permission': MANAGE_SETTINGS}])
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
    data = json.dumps([{'permission': MANAGE_SETTINGS}, {'permission': MANAGE_TEMPLATES}])
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
    data = json.dumps([{'permission': MANAGE_SETTINGS}])
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


@freeze_time("2016-01-01 11:09:00.061258")
def test_send_user_reset_password_should_send_reset_password_link(client,
                                                                  sample_user,
                                                                  mocker,
                                                                  password_reset_email_template):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    data = json.dumps({'email': sample_user.email_address})
    auth_header = create_authorization_header()
    resp = client.post(
        url_for('user.send_user_reset_password'),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 204
    notification = Notification.query.first()
    mocked.assert_called_once_with([str(notification.id)], queue="notify-internal-tasks")


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

    resp = client.post(
        url_for('user.send_already_registered_email', user_id=str(sample_user.id)),
        data=data,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204

    notification = Notification.query.first()
    mocked.assert_called_once_with(([str(notification.id)]), queue="notify-internal-tasks")


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

    resp = client.post(url_for('user.send_user_confirm_new_email', user_id=str(sample_user.id)),
                       data=data,
                       headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204
    notification = Notification.query.first()
    mocked.assert_called_once_with(
        ([str(notification.id)]),
        queue="notify-internal-tasks")


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
