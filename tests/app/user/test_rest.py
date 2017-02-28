import json
import pytest

from flask import url_for, current_app
from freezegun import freeze_time

import app
from app.models import (User, Permission, MANAGE_SETTINGS, MANAGE_TEMPLATES, Notification)
from app.dao.permissions_dao import default_service_permissions
from tests import create_authorization_header


def test_get_user_list(client, sample_service):
    """
    Tests GET endpoint '/' to retrieve entire user list.
    """
    header = create_authorization_header()
    response = client.get(url_for('user.get_user'),
                          headers=[header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 1
    sample_user = sample_service.users[0]
    expected_permissions = default_service_permissions
    fetched = json_resp['data'][0]

    assert str(sample_user.id) == fetched['id']
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
        "permissions": {}
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


def test_put_user(client, sample_service):
    """
    Tests PUT endpoint '/' to update a user.
    """
    assert User.query.count() == 1
    sample_user = sample_service.users[0]
    sample_user.failed_login_count = 1
    new_email = 'new@digital.cabinet-office.gov.uk'
    data = {
        'name': sample_user.name,
        'email_address': new_email,
        'mobile_number': sample_user.mobile_number
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.put(
        url_for('user.update_user', user_id=sample_user.id),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 200
    assert User.query.count() == 1
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data']['email_address'] == new_email
    expected_permissions = default_service_permissions
    fetched = json_resp['data']

    assert str(sample_user.id) == fetched['id']
    assert sample_user.name == fetched['name']
    assert sample_user.mobile_number == fetched['mobile_number']
    assert new_email == fetched['email_address']
    assert sample_user.state == fetched['state']
    assert sorted(expected_permissions) == sorted(fetched['permissions'][str(sample_service.id)])
    # password wasn't updated, so failed_login_count stays the same
    assert sample_user.failed_login_count == 1


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


def test_put_user_update_password(client, sample_service):
    """
    Tests PUT endpoint '/' to update a user including their password.
    """
    assert User.query.count() == 1
    sample_user = sample_service.users[0]
    new_password = '1234567890'
    data = {
        'name': sample_user.name,
        'email_address': sample_user.email_address,
        'mobile_number': sample_user.mobile_number,
        'password': new_password
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.put(
        url_for('user.update_user', user_id=sample_user.id),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 200
    assert User.query.count() == 1
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


def test_put_user_not_exists(client, sample_user, fake_uuid):
    """
    Tests PUT endpoint '/' to update a user doesn't exist.
    """
    assert User.query.count() == 1
    new_email = 'new@digital.cabinet-office.gov.uk'
    data = {'email_address': new_email}
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.put(
        url_for('user.update_user', user_id=fake_uuid),
        data=json.dumps(data),
        headers=headers)
    assert resp.status_code == 404
    assert User.query.count() == 1
    user = User.query.filter_by(id=str(sample_user.id)).first()
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['result'] == "error"
    assert json_resp['message'] == 'No result found'

    assert user == sample_user
    assert user.email_address != new_email


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


def test_get_user_with_permissions(client, sample_service_permission):
    header = create_authorization_header()
    response = client.get(url_for('user.get_user', user_id=str(sample_service_permission.user.id)),
                          headers=[header])
    assert response.status_code == 200
    permissions = json.loads(response.get_data(as_text=True))['data']['permissions']
    assert sample_service_permission.permission in permissions[str(sample_service_permission.service.id)]


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
    mocked.assert_called_once_with([str(notification.id)], queue="notify")


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
    mocked.assert_called_once_with(([str(notification.id)]), queue="notify")


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
        queue="notify")


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


def test_update_user_resets_failed_login_count_if_updating_password(client, sample_service):
    user = sample_service.users[0]
    user.failed_login_count = 1

    resp = client.put(
        url_for('user.update_user', user_id=user.id),
        data=json.dumps({
            'name': user.name,
            'email_address': user.email_address,
            'mobile_number': user.mobile_number,
            'password': 'foo'
        }),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )

    assert resp.status_code == 200
    assert user.failed_login_count == 0
