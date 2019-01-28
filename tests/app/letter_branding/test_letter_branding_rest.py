import json
import uuid

from app.models import LetterBranding
from tests import create_authorization_header
from tests.app.db import create_letter_branding


def test_get_all_letter_brands(client, notify_db_session):
    hm_gov = create_letter_branding()
    test_domain_branding = create_letter_branding(
        name='test domain', filename='test-domain', domain='test.domain'
    )
    response = client.get('/letter-branding', headers=[create_authorization_header()])
    assert response.status_code == 200
    json_response = json.loads(response.get_data(as_text=True))
    assert len(json_response) == 2
    for brand in json_response:
        if brand['id'] == str(hm_gov.id):
            assert hm_gov.serialize() == brand
        elif brand['id'] == str(test_domain_branding.id):
            assert test_domain_branding.serialize() == brand
        else:
            assert False


def test_get_letter_branding_by_id(client, notify_db_session):
    hm_gov = create_letter_branding()
    create_letter_branding(
        name='test domain', filename='test-domain', domain='test.domain'
    )
    response = client.get('/letter-branding/{}'.format(hm_gov.id), headers=[create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == hm_gov.serialize()


def test_get_letter_branding_by_id_returns_404_if_does_not_exist(client, notify_db_session):
    response = client.get('/letter-branding/{}'.format(uuid.uuid4()), headers=[create_authorization_header()])
    assert response.status_code == 404


def test_create_letter_branding(client, notify_db_session):
    form = {
        'name': 'super brand',
        'domain': 'super.brand',
        'filename': 'super-brand'
    }

    response = client.post(
        '/letter-branding',
        data=json.dumps(form),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
    )

    assert response.status_code == 201
    json_response = json.loads(response.get_data(as_text=True))
    letter_brand = LetterBranding.query.get(json_response['id'])
    assert letter_brand.name == form['name']
    assert letter_brand.domain == form['domain']
    assert letter_brand.filename == form['filename']


def test_create_letter_branding_returns_400_if_domain_already_exists(client, notify_db_session):
    create_letter_branding(name='duplicate', domain='duplicate', filename='duplicate')
    form = {
        'name': 'super brand',
        'domain': 'duplicate',
        'filename': 'super-brand',
    }

    response = client.post(
        '/letter-branding',
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(form)
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == {'domain': ["Domain already in use"]}


def test_update_letter_branding_returns_400_when_integrity_error_is_thrown(
        client, notify_db_session
):
    create_letter_branding(name='duplicate', domain='duplicate', filename='duplicate')
    brand_to_update = create_letter_branding(name='super brand', domain='super brand', filename='super brand')
    form = {
        'name': 'duplicate',
        'domain': 'super brand',
        'filename': 'super-brand',
    }

    response = client.post(
        '/letter-branding/{}'.format(brand_to_update.id),
        headers=[('Content-Type', 'application/json'), create_authorization_header()],
        data=json.dumps(form)
    )

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == {"name": ["Name already in use"]}
