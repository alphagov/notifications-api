from flask import json

from tests import create_authorization_header


def test_get_dvla_organisations(client):
    auth_header = create_authorization_header()

    response = client.get('/dvla_organisations', headers=[auth_header])

    assert response.status_code == 200
    dvla_organisations = json.loads(response.get_data(as_text=True))
    assert dvla_organisations == {'001': 'HM Government', '500': 'Land Registry'}
