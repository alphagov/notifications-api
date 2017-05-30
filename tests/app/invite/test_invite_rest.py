import json
import uuid

from app.models import Notification
from tests import create_authorization_header


def test_create_invited_user(client, sample_service, mocker, invitation_email_template):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'invited_user@service.gov.uk'
    invite_from = sample_service.users[0]

    data = {
        'service': str(sample_service.id),
        'email_address': email_address,
        'from_user': str(invite_from.id),
        'permissions': 'send_messages,manage_service,manage_api_keys'
    }
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/invite'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=json.dumps(data)
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))

    assert json_resp['data']['service'] == str(sample_service.id)
    assert json_resp['data']['email_address'] == email_address
    assert json_resp['data']['from_user'] == str(invite_from.id)
    assert json_resp['data']['permissions'] == 'send_messages,manage_service,manage_api_keys'
    assert json_resp['data']['id']

    notification = Notification.query.first()
    mocked.assert_called_once_with([(str(notification.id))], queue="notify-internal-tasks")


def test_create_invited_user_invalid_email(client, sample_service, mocker):
    mocked = mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    email_address = 'notanemail'
    invite_from = sample_service.users[0]

    data = {
        'service': str(sample_service.id),
        'email_address': email_address,
        'from_user': str(invite_from.id),
        'permissions': 'send_messages,manage_service,manage_api_keys'
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

    from tests.app.conftest import sample_invited_user
    invites = []
    for i in range(0, 5):
        email = 'invited_user_{}@service.gov.uk'.format(i)

        invited_user = sample_invited_user(notify_db,
                                           notify_db_session,
                                           sample_service,
                                           email)
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


def test_get_invited_user_by_service_and_id(client, sample_service, sample_invited_user):
    url = '/service/{}/invite/{}'.format(sample_service.id, sample_invited_user.id)

    auth_header = create_authorization_header()

    response = client.get(
        url,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    invite_email_address = sample_invited_user.email_address
    invite_from = sample_service.users[0]

    assert json_resp['data']['service'] == str(sample_service.id)
    assert json_resp['data']['email_address'] == invite_email_address
    assert json_resp['data']['from_user'] == str(invite_from.id)
    assert json_resp['data']['id']


def test_get_invited_user_by_service_but_unknown_invite_id_returns_404(client, sample_service):
    unknown_id = uuid.uuid4()
    url = '/service/{}/invite/{}'.format(sample_service.id, unknown_id)

    auth_header = create_authorization_header()

    response = client.get(
        url,
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    assert response.status_code == 404


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
