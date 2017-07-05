from flask import json

from app.models import Organisation

from tests import create_authorization_header


def test_get_organisations(notify_api, notify_db, notify_db_session):
    org1 = Organisation(colour='#FFFFFF', logo='/path/image.png', name='Org1')
    org2 = Organisation(colour='#000000', logo='/path/other.png', name='Org2')
    notify_db.session.add_all([org1, org2])
    notify_db.session.commit()

    with notify_api.test_request_context(), notify_api.test_client() as client:
        auth_header = create_authorization_header()
        response = client.get('/organisation', headers=[auth_header])

    assert response.status_code == 200
    organisations = json.loads(response.get_data(as_text=True))['organisations']
    assert len(organisations) == 2
    assert {org['id'] for org in organisations} == {str(org1.id), str(org2.id)}


def test_get_organisation_by_id(notify_api, notify_db, notify_db_session):
    org = Organisation(colour='#FFFFFF', logo='/path/image.png', name='My Org')
    notify_db.session.add(org)
    notify_db.session.commit()

    with notify_api.test_request_context(), notify_api.test_client() as client:
        auth_header = create_authorization_header()
        response = client.get('/organisation/{}'.format(org.id), headers=[auth_header])

    assert response.status_code == 200
    organisation = json.loads(response.get_data(as_text=True))['organisation']
    assert set(organisation.keys()) == {'colour', 'logo', 'name', 'id'}
    assert organisation['colour'] == '#FFFFFF'
    assert organisation['logo'] == '/path/image.png'
    assert organisation['name'] == 'My Org'
    assert organisation['id'] == str(org.id)


def test_create_organisation(client, notify_db, notify_db_session):
    data = {
        'name': 'test organisation',
        'colour': '#0000ff',
        'logo': '/images/test_x2.png'
    }
    auth_header = create_authorization_header()

    response = client.post(
        '/organisation',
        headers=[('Content-Type', 'application/json'), auth_header],
        data=json.dumps(data)
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert data['name'] == json_resp['data']['name']
