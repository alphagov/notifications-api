import json
import uuid

from datetime import datetime, timedelta

from app import encryption
from tests import create_authorization_header
import app.celery.tasks


def test_create_invited_user(notify_api, sample_service, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.email_invited_user.apply_async')
            mocker.patch('utils.url_safe_token.generate_token', return_value='the-token')
            email_address = 'invited_user@service.gov.uk'
            invite_from = sample_service.users[0]

            data = {
                'service': str(sample_service.id),
                'email_address': email_address,
                'from_user': invite_from.id,
                'permissions': 'send_messages,manage_service,manage_api_keys'
            }

            data = json.dumps(data)

            auth_header = create_authorization_header(
                path='/service/{}/invite'.format(sample_service.id),
                method='POST',
                request_body=data
            )

            response = client.post(
                '/service/{}/invite'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            assert response.status_code == 201
            json_resp = json.loads(response.get_data(as_text=True))

            assert json_resp['data']['service'] == str(sample_service.id)
            assert json_resp['data']['email_address'] == email_address
            assert json_resp['data']['from_user'] == invite_from.id
            assert json_resp['data']['permissions'] == 'send_messages,manage_service,manage_api_keys'
            assert json_resp['data']['id']
            invitation_expiration_days = notify_api.config['INVITATION_EXPIRATION_DAYS']
            expiry_date = (datetime.now() + timedelta(days=invitation_expiration_days)).replace(hour=0, minute=0,
                                                                                                second=0,
                                                                                                microsecond=0)
            encrypted_invitation = {'to': email_address,
                                    'user_name': invite_from.name,
                                    'service_id': str(sample_service.id),
                                    'service_name': sample_service.name,
                                    'token': 'the-token',
                                    'expiry_date': str(expiry_date)
                                    }
            app.celery.tasks.email_invited_user.apply_async.assert_called_once_with(
                [encryption.encrypt(encrypted_invitation)],
                queue='email-invited-user')


def test_create_invited_user_invalid_email(notify_api, sample_service, mocker):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            mocker.patch('app.celery.tasks.email_invited_user.apply_async')
            email_address = 'notanemail'
            invite_from = sample_service.users[0]

            data = {
                'service': str(sample_service.id),
                'email_address': email_address,
                'from_user': invite_from.id,
                'permissions': 'send_messages,manage_service,manage_api_keys'
            }

            data = json.dumps(data)

            auth_header = create_authorization_header(
                path='/service/{}/invite'.format(sample_service.id),
                method='POST',
                request_body=data
            )

            response = client.post(
                '/service/{}/invite'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            assert response.status_code == 400
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == {'email_address': ['Not a valid email address']}
            app.celery.tasks.email_invited_user.apply_async.assert_not_called()


def test_get_all_invited_users_by_service(notify_api, notify_db, notify_db_session, sample_service):

    from tests.app.conftest import sample_invited_user
    invites = []
    for i in range(0, 5):
        email = 'invited_user_{}@service.gov.uk'.format(i)

        invited_user = sample_invited_user(notify_db,
                                           notify_db_session,
                                           sample_service,
                                           email)
        invites.append(invited_user)

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            url = '/service/{}/invite'.format(sample_service.id)

            auth_header = create_authorization_header(
                path=url,
                method='GET'
            )

            response = client.get(
                url,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))

            invite_from = sample_service.users[0]

            for invite in json_resp['data']:
                assert invite['service'] == str(sample_service.id)
                assert invite['from_user'] == invite_from.id
                assert invite['id']


def test_get_invited_users_by_service_with_no_invites(notify_api, notify_db, notify_db_session, sample_service):

    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            url = '/service/{}/invite'.format(sample_service.id)

            auth_header = create_authorization_header(
                path=url,
                method='GET'
            )

            response = client.get(
                url,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 0


def test_get_invited_user_by_service_and_id(notify_api, sample_service, sample_invited_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            url = '/service/{}/invite/{}'.format(sample_service.id, sample_invited_user.id)

            auth_header = create_authorization_header(
                path=url,
                method='GET'
            )

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
            assert json_resp['data']['from_user'] == invite_from.id
            assert json_resp['data']['id']


def test_get_invited_user_by_service_but_unknown_invite_id_returns_404(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            unknown_id = uuid.uuid4()
            url = '/service/{}/invite/{}'.format(sample_service.id, unknown_id)

            auth_header = create_authorization_header(
                path=url,
                method='GET'
            )

            response = client.get(
                url,
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert response.status_code == 404


def test_update_invited_user_set_status_to_cancelled(notify_api, sample_invited_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            data = {'status': 'cancelled'}
            url = '/service/{0}/invite/{1}'.format(sample_invited_user.service_id, sample_invited_user.id)
            auth_header = create_authorization_header(
                path=url,
                method='POST',
                request_body=json.dumps(data)
            )
            response = client.post(url,
                                   data=json.dumps(data),
                                   headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))['data']
            assert json_resp['status'] == 'cancelled'


def test_update_invited_user_for_wrong_service_returns_404(notify_api, sample_invited_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {'status': 'cancelled'}
            bad_service_id = uuid.uuid4()
            url = '/service/{0}/invite/{1}'.format(bad_service_id, sample_invited_user.id)
            auth_header = create_authorization_header(
                path=url,
                method='POST',
                request_body=json.dumps(data)
            )
            response = client.post(url, data=json.dumps(data),
                                   headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 404
            json_response = json.loads(response.get_data(as_text=True))['message']
            assert json_response == 'No result found'


def test_update_invited_user_for_invalid_data_returns_400(notify_api, sample_invited_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {'status': 'garbage'}
            url = '/service/{0}/invite/{1}'.format(sample_invited_user.service_id, sample_invited_user.id)
            auth_header = create_authorization_header(
                path=url,
                method='POST',
                request_body=json.dumps(data)
            )
            response = client.post(url, data=json.dumps(data),
                                   headers=[('Content-Type', 'application/json'), auth_header])
            assert response.status_code == 400
