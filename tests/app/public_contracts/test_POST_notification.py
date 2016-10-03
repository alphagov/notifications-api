from flask import json

from . import validate
from tests import create_authorization_header


def test_post_sms_contract(client, mocker, sample_template):
    mocker.patch('app.celery.provider_tasks.deliver_sms.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

    data = {
        'to': '07700 900 855',
        'template': str(sample_template.id)
    }

    auth_header = create_authorization_header(service_id=sample_template.service_id)

    response = client.post(
        path='/notifications/sms',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    validate(response.get_data(as_text=True), 'POST_notification_return_sms.json')


def test_post_email_contract(client, mocker, sample_email_template):
    mocker.patch('app.celery.provider_tasks.deliver_email.apply_async')
    mocker.patch('app.encryption.encrypt', return_value="something_encrypted")

    data = {
        'to': 'foo@bar.com',
        'template': str(sample_email_template.id)
    }

    auth_header = create_authorization_header(service_id=sample_email_template.service_id)

    response = client.post(
        path='/notifications/email',
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    validate(response.get_data(as_text=True), 'POST_notification_return_email.json')
