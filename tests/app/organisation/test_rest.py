from app.models import Organisation
from tests.app.db import create_organisation


def test_get_all_organisations(admin_request, notify_db_session):
    create_organisation(name='inactive org', active=False)
    create_organisation(name='active org')

    response = admin_request.get(
        'organisation.get_organisations',
        _expected_status=200
    )

    assert len(response) == 2
    assert response[0]['name'] == 'active org'
    assert response[0]['active'] is True
    assert response[1]['name'] == 'inactive org'
    assert response[1]['active'] is False


def test_get_organisation_by_id(admin_request, notify_db_session):
    org = create_organisation()

    response = admin_request.get(
        'organisation.get_organisation_by_id',
        _expected_status=200,
        organisation_id=org.id
    )

    assert set(response.keys()) == {'id', 'name', 'active'}
    assert response['id'] == str(org.id)
    assert response['name'] == 'test_org_1'
    assert response['active'] is True


def test_post_create_organisation(admin_request, notify_db_session):
    data = {
        'name': 'test organisation',
        'active': True
    }

    response = admin_request.post(
        'organisation.create_organisation',
        _data=data,
        _expected_status=201
    )

    organisation = Organisation.query.all()

    assert data['name'] == response['name']
    assert data['active'] == response['active']
    assert len(organisation) == 1


def test_post_create_organisation_with_missing_name_gives_validation_error(admin_request, notify_db_session):
    data = {
        'active': False
    }

    response = admin_request.post(
        'organisation.create_organisation',
        _data=data,
        _expected_status=400
    )

    assert len(response['errors']) == 1
    assert response['errors'][0]['error'] == 'ValidationError'
    assert response['errors'][0]['message'] == 'name is a required property'


def test_post_update_organisation_updates_fields(admin_request, notify_db_session):
    org = create_organisation()
    data = {
        'name': 'new organisation name',
        'active': False
    }

    admin_request.post(
        'organisation.update_organisation',
        _data=data,
        organisation_id=org.id,
        _expected_status=204
    )

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert organisation[0].id == org.id
    assert organisation[0].name == data['name']
    assert organisation[0].active == data['active']


def test_post_update_organisation_gives_404_status_if_org_does_not_exist(admin_request, notify_db_session):
    data = {'name': 'new organisation name'}

    admin_request.post(
        'organisation.update_organisation',
        _data=data,
        organisation_id='31d42ce6-3dac-45a7-95cb-94423d5ca03c',
        _expected_status=404
    )

    organisation = Organisation.query.all()

    assert not organisation
