import os

from flask import json
import jsonschema

from tests import create_authorization_header


def test_get_sms_contract(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_notification.id), headers=[auth_header])

    with open(os.path.join(os.path.dirname(__file__), './GET_notification_return_sms.json')) as schema:
        jsonschema.validate(
            json.loads(response.get_data(as_text=True)),
            json.load(schema),
            format_checker=jsonschema.FormatChecker()
        )


def test_get_email_contract(client, sample_email_notification):
    auth_header = create_authorization_header(service_id=sample_email_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_email_notification.id), headers=[auth_header])

    with open(os.path.join(os.path.dirname(__file__), './GET_notification_return_email.json')) as schema:
        jsonschema.validate(
            json.loads(response.get_data(as_text=True)),
            json.load(schema),
            format_checker=jsonschema.FormatChecker()
        )
