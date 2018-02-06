import json

import pytest

from app.models import EmailBranding

from tests import create_authorization_header


def test_get_email_branding_options(admin_request, notify_db, notify_db_session):
    email_branding1 = EmailBranding(colour='#FFFFFF', logo='/path/image.png', name='Org1')
    email_branding2 = EmailBranding(colour='#000000', logo='/path/other.png', name='Org2')
    notify_db.session.add_all([email_branding1, email_branding2])
    notify_db.session.commit()

    email_branding = admin_request.get(
        'email_branding.get_email_branding_options'
    )['email_branding']

    assert len(email_branding) == 2
    assert {
        email_branding['id'] for email_branding in email_branding
    } == {
        str(email_branding1.id), str(email_branding2.id)
    }


def test_get_email_branding_options_from_old_endpoint(client, notify_db, notify_db_session):
    email_branding1 = EmailBranding(colour='#FFFFFF', logo='/path/image.png', name='Org1')
    email_branding2 = EmailBranding(colour='#000000', logo='/path/other.png', name='Org2')
    notify_db.session.add_all([email_branding1, email_branding2])
    notify_db.session.commit()

    response = client.get(
        '/organisation',
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    email_branding = json_resp['organisations']

    assert len(email_branding) == 2
    assert {
        email_branding['id'] for email_branding in email_branding
    } == {
        str(email_branding1.id), str(email_branding2.id)
    }


def test_get_email_branding_by_id(admin_request, notify_db, notify_db_session):
    email_branding = EmailBranding(colour='#FFFFFF', logo='/path/image.png', name='My Org')
    notify_db.session.add(email_branding)
    notify_db.session.commit()

    response = admin_request.get(
        'email_branding.get_email_branding_by_id',
        _expected_status=200,
        email_branding_id=email_branding.id
    )

    assert set(response['email_branding'].keys()) == {'colour', 'logo', 'name', 'id'}
    assert response['email_branding']['colour'] == '#FFFFFF'
    assert response['email_branding']['logo'] == '/path/image.png'
    assert response['email_branding']['name'] == 'My Org'
    assert response['email_branding']['id'] == str(email_branding.id)


def test_get_email_branding_by_id_from_old_endpoint(client, notify_db, notify_db_session):
    email_branding = EmailBranding(colour='#FFFFFF', logo='/path/image.png', name='My Org')
    notify_db.session.add(email_branding)
    notify_db.session.commit()

    response = client.get(
        '/organisation/{}'.format(email_branding.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))

    assert json_resp['organisation']['id'] == str(email_branding.id)


def test_post_create_email_branding(admin_request, notify_db_session):
    data = {
        'name': 'test email_branding',
        'colour': '#0000ff',
        'logo': '/images/test_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )
    assert data['name'] == response['data']['name']
    assert data['colour'] == response['data']['colour']
    assert data['logo'] == response['data']['logo']


def test_post_create_email_branding_without_logo_is_ok(admin_request, notify_db_session):
    data = {
        'name': 'test email_branding',
        'colour': '#0000ff',
    }
    admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201,
    )


def test_post_create_email_branding_without_name_or_colour_is_valid(admin_request, notify_db_session):
    data = {
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    assert response['data']['logo'] == data['logo']
    assert response['data']['name'] is None
    assert response['data']['colour'] is None


@pytest.mark.parametrize('data_update', [
    ({'name': 'test email_branding 1'}),
    ({'logo': 'images/text_x3.png', 'colour': '#ffffff'}),
])
def test_post_update_email_branding_updates_field(admin_request, notify_db_session, data_update):
    data = {
        'name': 'test email_branding',
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'email_branding.create_email_branding',
        _data=data,
        _expected_status=201
    )

    email_branding_id = response['data']['id']

    response = admin_request.post(
        'email_branding.update_email_branding',
        _data=data_update,
        email_branding_id=email_branding_id
    )

    email_branding = EmailBranding.query.all()

    assert len(email_branding) == 1
    assert str(email_branding[0].id) == email_branding_id
    for key in data_update.keys():
        assert getattr(email_branding[0], key) == data_update[key]
