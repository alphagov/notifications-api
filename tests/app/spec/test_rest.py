import flex
import pytest

from flask import json
from tests import create_authorization_header


def test_spec_returns_valid_json(notify_api, sample_notification):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(service_id=sample_notification.service_id)

            response = client.get('/spec', headers=[auth_header])

            # Check that it’s a valid Swagger schema
            flex.load(
                json.loads(response.get_data(as_text=True))
            )
