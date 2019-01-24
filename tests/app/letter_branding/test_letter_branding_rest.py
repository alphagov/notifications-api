from tests import create_authorization_header
from tests.app.db import create_letter_branding


def test_get_letter_brandings(client, notify_db_session):
    platform_default = create_letter_branding()
    test_domain_branding = create_letter_branding(
        name='test domain', filename='test-domain', domain='test.domain', platform_default=False
    )
    response = client.get('/letter-branding', headers=[create_authorization_header()])
    assert response.status_code == 200
    json_response = response.get_data(as_text=True)
    assert platform_default.serialize() in json_response
    assert test_domain_branding.serialize() in json_response
