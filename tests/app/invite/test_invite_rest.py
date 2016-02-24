import json

from tests import create_authorization_header


def test_create_invited_user(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            email_address = 'invited_user@service.gov.uk'
            invite_from = sample_service.users[0]

            data = {
                'service': str(sample_service.id),
                'email_address': email_address,
                'from_user': invite_from.id
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
            assert json_resp['data']['id']


def test_create_invited_user_invalid_email(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            email_address = 'notanemail'
            invite_from = sample_service.users[0]

            data = {
                'service': str(sample_service.id),
                'email_address': email_address,
                'from_user': invite_from.id
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
            assert json_resp['message'] == {'email_address': ['Invalid email']}
