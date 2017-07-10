from flask import json
import pytest

from app.models import Organisation

from tests import create_authorization_header


def test_get_organisations(admin_request, notify_db, notify_db_session):
    org1 = Organisation(colour='#FFFFFF', logo='/path/image.png', name='Org1')
    org2 = Organisation(colour='#000000', logo='/path/other.png', name='Org2')
    notify_db.session.add_all([org1, org2])
    notify_db.session.commit()

    organisations = admin_request.get(
        'organisation.get_organisations'
    )['organisations']

    assert len(organisations) == 2
    assert {org['id'] for org in organisations} == {str(org1.id), str(org2.id)}


def test_get_organisation_by_id(admin_request, notify_db, notify_db_session):
    org = Organisation(colour='#FFFFFF', logo='/path/image.png', name='My Org')
    notify_db.session.add(org)
    notify_db.session.commit()

    response = admin_request.get(
        'organisation.get_organisation_by_id',
        _expected_status=200,
        org_id=org.id
    )

    assert set(response['organisation'].keys()) == {'colour', 'logo', 'name', 'id'}
    assert response['organisation']['colour'] == '#FFFFFF'
    assert response['organisation']['logo'] == '/path/image.png'
    assert response['organisation']['name'] == 'My Org'
    assert response['organisation']['id'] == str(org.id)


def test_post_create_organisation(admin_request, notify_db_session):
    data = {
        'name': 'test organisation',
        'colour': '#0000ff',
        'logo': '/images/test_x2.png'
    }
    response = admin_request.post(
        'organisation.create_organisation',
        _data=data,
        _expected_status=201
    )
    assert data['name'] == response['data']['name']
    assert data['colour'] == response['data']['colour']
    assert data['logo'] == response['data']['logo']


def test_post_create_organisation_without_logo_raises_error(admin_request, notify_db_session):
    data = {
        'name': 'test organisation',
        'colour': '#0000ff',
    }
    response = admin_request.post(
        'organisation.create_organisation',
        _data=data,
        _expected_status=400
    )
    assert response['errors'][0]['message'] == "logo is a required property"


def test_post_create_organisation_without_name_or_colour_is_valid(admin_request, notify_db_session):
    data = {
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'organisation.create_organisation',
        _data=data,
        _expected_status=201
    )

    assert response['data']['logo'] == data['logo']
    assert response['data']['name'] is None
    assert response['data']['colour'] is None


@pytest.mark.parametrize('data_update', [
    ({'name': 'test organisation 1'}),
    ({'logo': 'images/text_x3.png', 'colour': '#ffffff'})
])
def test_post_update_organisation_updates_field(admin_request, notify_db_session, data_update):
    data = {
        'name': 'test organisation',
        'logo': 'images/text_x2.png'
    }
    response = admin_request.post(
        'organisation.create_organisation',
        _data=data,
        _expected_status=201
    )

    org_id = response['data']['id']

    response = admin_request.post(
        'organisation.update_organisation',
        _data=data_update,
        organisation_id=org_id
    )

    organisations = Organisation.query.all()

    assert len(organisations) == 1
    assert str(organisations[0].id) == org_id
    for key in data_update.keys():
        assert getattr(organisations[0], key) == data_update[key]
