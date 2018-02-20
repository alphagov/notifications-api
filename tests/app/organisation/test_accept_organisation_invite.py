import json

from flask import current_app
from notifications_utils.url_safe_token import generate_token

from tests import create_authorization_header


def test_accept_organisation_invitation(client, sample_invited_org_user):
    token = generate_token(str(sample_invited_org_user.id), current_app.config['SECRET_KEY'],
                           current_app.config['DANGEROUS_SALT'])
    url = '/organisation-invitation/{}'.format(token)
    auth_header = create_authorization_header()
    response = client.get(url, headers=[('Content-Type', 'application/json'), auth_header])
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['data'] == sample_invited_org_user.serialize()

