from app.models import Organisation
from app.dao.organisation_dao import dao_add_service_to_organisation
from tests.app.db import create_organisation, create_service


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


def test_post_link_service_to_organisation(admin_request, sample_service, sample_organisation):
    data = {
        'service_id': str(sample_service.id)
    }

    admin_request.post(
        'organisation.link_service_to_organisation',
        _data=data,
        organisation_id=sample_organisation.id,
        _expected_status=204
    )

    assert len(sample_organisation.services) == 1


def test_post_link_service_to_another_org(
        admin_request, sample_service, sample_organisation):
    data = {
        'service_id': str(sample_service.id)
    }

    admin_request.post(
        'organisation.link_service_to_organisation',
        _data=data,
        organisation_id=sample_organisation.id,
        _expected_status=204
    )

    assert len(sample_organisation.services) == 1

    new_org = create_organisation()
    admin_request.post(
        'organisation.link_service_to_organisation',
        _data=data,
        organisation_id=new_org.id,
        _expected_status=204
    )
    assert not sample_organisation.services
    assert len(new_org.services) == 1


def test_post_link_service_to_organisation_nonexistent_organisation(
        admin_request, sample_service, fake_uuid):
    data = {
        'service_id': str(sample_service.id)
    }

    admin_request.post(
        'organisation.link_service_to_organisation',
        _data=data,
        organisation_id=fake_uuid,
        _expected_status=404
    )


def test_post_link_service_to_organisation_nonexistent_service(
        admin_request, sample_organisation, fake_uuid):
    data = {
        'service_id': fake_uuid
    }

    admin_request.post(
        'organisation.link_service_to_organisation',
        _data=data,
        organisation_id=str(sample_organisation.id),
        _expected_status=404
    )


def test_post_link_service_to_organisation_missing_payload(
        admin_request, sample_organisation, fake_uuid):
    admin_request.post(
        'organisation.link_service_to_organisation',
        organisation_id=str(sample_organisation.id),
        _expected_status=400
    )


def test_rest_get_organisation_services(
        admin_request, sample_organisation, sample_service):
    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    response = admin_request.get(
        'organisation.get_organisation_services',
        organisation_id=str(sample_organisation.id),
        _expected_status=200
    )

    assert response == [sample_service.serialize_for_org_dashboard()]


def test_rest_get_organisation_services_is_ordered_by_name(
        admin_request, sample_organisation, sample_service):
    service_2 = create_service(service_name='service 2')
    service_1 = create_service(service_name='service 1')
    dao_add_service_to_organisation(service_1, sample_organisation.id)
    dao_add_service_to_organisation(service_2, sample_organisation.id)
    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    response = admin_request.get(
        'organisation.get_organisation_services',
        organisation_id=str(sample_organisation.id),
        _expected_status=200
    )

    assert response[0]['name'] == sample_service.name
    assert response[1]['name'] == service_1.name
    assert response[2]['name'] == service_2.name


def test_rest_get_organisation_services_inactive_services_at_end(
        admin_request, sample_organisation):
    inactive_service = create_service(service_name='inactive service', active=False)
    service = create_service()
    inactive_service_1 = create_service(service_name='inactive service 1', active=False)

    dao_add_service_to_organisation(inactive_service, sample_organisation.id)
    dao_add_service_to_organisation(service, sample_organisation.id)
    dao_add_service_to_organisation(inactive_service_1, sample_organisation.id)

    response = admin_request.get(
        'organisation.get_organisation_services',
        organisation_id=str(sample_organisation.id),
        _expected_status=200
    )

    assert response[0]['name'] == service.name
    assert response[1]['name'] == inactive_service.name
    assert response[2]['name'] == inactive_service_1.name
