import uuid

from flask import json
from freezegun import freeze_time
from notifications_utils.url_safe_token import generate_token
from tests import create_authorization_header


def test_accept_invite_for_expired_token_returns_400(notify_api, sample_invited_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            with freeze_time('2016-01-01T12:00:00'):
                token = generate_token(str(sample_invited_user.id), notify_api.config['SECRET_KEY'],
                                       notify_api.config['DANGEROUS_SALT'])
        url = '/invite/{}'.format(token)
        auth_header = create_authorization_header()
        response = client.get(url, headers=[('Content-Type', 'application/json'), auth_header])

        assert response.status_code == 400
        json_resp = json.loads(response.get_data(as_text=True))
        assert json_resp['result'] == 'error'
        assert json_resp['message'] == {'invitation': [
            'Your invitation to GOV.UK Notify has expired. '
            'Please ask the person that invited you to send you another one']}


def test_accept_invite_returns_200_when_token_valid(notify_api, sample_invited_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = generate_token(str(sample_invited_user.id), notify_api.config['SECRET_KEY'],
                                   notify_api.config['DANGEROUS_SALT'])
            url = '/invite/{}'.format(token)
            auth_header = create_authorization_header()
            response = client.get(url, headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['data']['id'] == str(sample_invited_user.id)
            assert json_resp['data']['email_address'] == sample_invited_user.email_address
            assert json_resp['data']['from_user'] == str(sample_invited_user.user_id)
            assert json_resp['data']['service'] == str(sample_invited_user.service_id)
            assert json_resp['data']['status'] == sample_invited_user.status
            assert json_resp['data']['permissions'] == sample_invited_user.permissions


def test_accept_invite_returns_400_when_invited_user_does_not_exist(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            token = generate_token(str(uuid.uuid4()), notify_api.config['SECRET_KEY'],
                                   notify_api.config['DANGEROUS_SALT'])
            url = '/invite/{}'.format(token)
            auth_header = create_authorization_header()
            response = client.get(url, headers=[('Content-Type', 'application/json'), auth_header])

            assert response.status_code == 404
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'
