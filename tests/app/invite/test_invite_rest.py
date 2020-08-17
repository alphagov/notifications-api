import json
import pytest

from app.models import Notification, SMS_AUTH_TYPE, EMAIL_AUTH_TYPE
from tests import create_authorization_header
from tests.app.db import create_invited_user


@pytest.mark.parametrize('extra_args, expected_start_of_invite_url', [
    (
        {},
        'http://localhost:6012/invitation/'
    ),
    (
        {'invite_link_host': 'https://www.example.com'},
        'https://www.example.com/invitation/'
    ),
])
def test_create_invited_user(
    admin_request,
    sample_service,
    mocker,
    invitation_email_template,
    extra_args,
    expected_start_of_invite_url,
):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'invited_user@service.gov.uk'
    invite_from = sample_service.users[0]

    data = dict(
        service=str(sample_service.id),
        email_address=email_address,
        from_user=str(invite_from.id),
        permissions='send_messages,manage_service,manage_api_keys',
        auth_type=EMAIL_AUTH_TYPE,
        folder_permissions=['folder_1', 'folder_2', 'folder_3'],
        **extra_args
    )

    json_resp = admin_request.post(
        'invite.create_invited_user',
        service_id=sample_service.id,
        _data=data,
        _expected_status=201
    )

    assert json_resp['data']['service'] == str(sample_service.id)
    assert json_resp['data']['email_address'] == email_address
    assert json_resp['data']['from_user'] == str(invite_from.id)
    assert json_resp['data']['permissions'] == 'send_messages,manage_service,manage_api_keys'
    assert json_resp['data']['auth_type'] == EMAIL_AUTH_TYPE
    assert json_resp['data']['id']
    assert json_resp['data']['folder_permissions'] == ['folder_1', 'folder_2', 'folder_3']

    notification = Notification.query.first()

    assert notification.reply_to_text == invite_from.email_address

    assert len(notification.personalisation.keys()) == 3
    assert notification.personalisation['service_name'] == 'Sample service'
    assert notification.personalisation['user_name'] == 'Test User'
    assert notification.personalisation['url'].startswith(expected_start_of_invite_url)
    assert len(notification.personalisation['url']) > len(expected_start_of_invite_url)

    mocked.assert_called_once_with([(str(notification.id))], queue="notify-internal-tasks")


def test_create_invited_user_without_auth_type(admin_request, sample_service, mocker, invitation_email_template):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'invited_user@service.gov.uk'
    invite_from = sample_service.users[0]

    data = {
        'service': str(sample_service.id),
        'email_address': email_address,
        'from_user': str(invite_from.id),
        'permissions': 'send_messages,manage_service,manage_api_keys',
        'folder_permissions': []
    }

    json_resp = admin_request.post(
        'invite.create_invited_user',
        service_id=sample_service.id,
        _data=data,
        _expected_status=201
    )

    assert json_resp['data']['auth_type'] == SMS_AUTH_TYPE


def test_create_invited_user_invalid_email(client, sample_service, mocker, fake_uuid):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'notanemail'
    invite_from = sample_service.users[0]

    data = {
        'service': str(sample_service.id),
        'email_address': email_address,
        'from_user': str(invite_from.id),
        'permissions': 'send_messages,manage_service,manage_api_keys',
        'folder_permissions': [fake_uuid, fake_uuid]
    }

    data = json.dumps(data)

    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/invite'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == {'email_address': ['Not a valid email address']}
    assert mocked.call_count == 0


def test_get_all_invited_users_by_service(client, notify_db, notify_db_session, sample_service):
    invites = []
    for i in range(0, 5):
        email = 'invited_user_{}@service.gov.uk'.format(i)
        invited_user = create_invited_user(sample_service, to_email_address=email)

        invites.append(invited_user)

    url = '/service/{}/invite'.format(sample_service.id)

    auth_header = create_authorization_header()

    response = client.get(
        url,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    invite_from = sample_service.users[0]

    for invite in json_resp['data']:
        assert invite['service'] == str(sample_service.id)
        assert invite['from_user'] == str(invite_from.id)
        assert invite['auth_type'] == SMS_AUTH_TYPE
        assert invite['id']


def test_get_invited_users_by_service_with_no_invites(client, notify_db, notify_db_session, sample_service):
    url = '/service/{}/invite'.format(sample_service.id)

    auth_header = create_authorization_header()

    response = client.get(
        url,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 0


def test_get_invited_user_by_service(admin_request, sample_invited_user):
    json_resp = admin_request.get(
        'invite.get_invited_user_by_service',
        service_id=sample_invited_user.service.id,
        invited_user_id=sample_invited_user.id
    )
    assert json_resp['data']['email_address'] == sample_invited_user.email_address


def test_get_invited_user_by_service_when_user_does_not_belong_to_the_service(
    admin_request,
    sample_invited_user,
    fake_uuid,
):
    json_resp = admin_request.get(
        'invite.get_invited_user_by_service',
        service_id=fake_uuid,
        invited_user_id=sample_invited_user.id,
        _expected_status=404
    )
    assert json_resp['result'] == 'error'


def test_update_invited_user_set_status_to_cancelled(client, sample_invited_user):
    data = {'status': 'cancelled'}
    url = '/service/{0}/invite/{1}'.format(sample_invited_user.service_id, sample_invited_user.id)
    auth_header = create_authorization_header()
    response = client.post(url,
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))['data']
    assert json_resp['status'] == 'cancelled'


def test_update_invited_user_for_wrong_service_returns_404(client, sample_invited_user, fake_uuid):
    data = {'status': 'cancelled'}
    url = '/service/{0}/invite/{1}'.format(fake_uuid, sample_invited_user.id)
    auth_header = create_authorization_header()
    response = client.post(url, data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 404
    json_response = json.loads(response.get_data(as_text=True))['message']
    assert json_response == 'No result found'


def test_update_invited_user_for_invalid_data_returns_400(client, sample_invited_user):
    data = {'status': 'garbage'}
    url = '/service/{0}/invite/{1}'.format(sample_invited_user.service_id, sample_invited_user.id)
    auth_header = create_authorization_header()
    response = client.post(url, data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 400
