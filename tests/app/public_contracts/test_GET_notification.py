import os

from flask import json
import jsonschema

from tests import create_authorization_header

def validate(json_string, schema_filename):
    resolver = jsonschema.RefResolver('file://' + os.path.dirname(__file__) + '/', None)
    with open(os.path.join(os.path.dirname(__file__), schema_filename)) as schema:
        jsonschema.validate(
            json.loads(json_string),
            json.load(schema),
            format_checker=jsonschema.FormatChecker(),
            resolver=resolver
        )

def test_get_sms_contract(client, sample_notification):
    auth_header = create_authorization_header(service_id=sample_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_notification.id), headers=[auth_header])

    validate(response.get_data(as_text=True), './GET_notification_return_sms.json')


def test_get_email_contract(client, sample_email_notification):
    auth_header = create_authorization_header(service_id=sample_email_notification.service_id)
    response = client.get('/notifications/{}'.format(sample_email_notification.id), headers=[auth_header])

    validate(response.get_data(as_text=True), './GET_notification_return_email.json')
