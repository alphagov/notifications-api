import uuid

from app.models import ServiceContactList
from tests.app.db import (
    create_job,
    create_service_contact_list,
    create_service,
    create_template,
)


def test_create_service_contact_list(sample_service, admin_request):
    data = {
        "id": str(uuid.uuid4()),
        "row_count": 100,
        "original_file_name": "staff_emergency_list.xls",
        "template_type": 'email',
        "created_by": str(sample_service.users[0].id)
    }

    response = admin_request.post(
        'service.create_contact_list',
        _data=data,
        service_id=sample_service.id,
        _expected_status=201
    )

    assert response['id'] == data['id']
    assert response['original_file_name'] == 'staff_emergency_list.xls'
    assert response['row_count'] == 100
    assert response['template_type'] == 'email'
    assert response['service_id'] == str(sample_service.id)
    assert response['created_at']

    db_results = ServiceContactList.query.all()
    assert len(db_results) == 1
    assert str(db_results[0].id) == data['id']


def test_create_service_contact_list_cannot_save_type_letter(sample_service, admin_request):
    data = {
        "id": str(uuid.uuid4()),
        "row_count": 100,
        "original_file_name": "staff_emergency_list.xls",
        "template_type": 'letter',
        "created_by": str(sample_service.users[0].id)
    }

    response = admin_request.post(
        'service.create_contact_list',
        _data=data,
        service_id=sample_service.id,
        _expected_status=400
    )
    assert response['errors'][0]['message'] == "template_type letter is not one of [email, sms]"


def test_get_contact_list(admin_request, notify_db_session):
    contact_list = create_service_contact_list()

    response = admin_request.get(
        'service.get_contact_list',
        service_id=contact_list.service_id
    )

    assert len(response) == 1
    assert response[0] == contact_list.serialize()


def test_get_contact_list_returns_for_service(admin_request, notify_db_session):
    service_1 = create_service(service_name='Service under test')
    service_2 = create_service(service_name='Service should return results')

    expected_list_1 = create_service_contact_list(service=service_1)
    expected_list_2 = create_service_contact_list(service=service_1)
    # not included in results
    create_service_contact_list(service=service_2)

    response = admin_request.get(
        'service.get_contact_list',
        service_id=service_1.id
    )

    assert len(response) == 2
    assert response[0] == expected_list_2.serialize()
    assert response[1] == expected_list_1.serialize()


def test_dao_get_contact_list_by_id(admin_request, sample_service):
    service_1 = create_service(service_name='Service under test')

    expected_list_1 = create_service_contact_list(service=service_1)
    create_service_contact_list(service=service_1)

    response = admin_request.get(
        'service.get_contact_list_by_id',
        service_id=service_1.id,
        contact_list_id=expected_list_1.id
    )

    assert response == expected_list_1.serialize()


def test_dao_get_contact_list_by_id_does_not_return_if_contact_list_id_for_another_service(
    admin_request, sample_service
):
    service_1 = create_service(service_name='Service requesting list')
    service_2 = create_service(service_name='Service that owns the list')

    create_service_contact_list(service=service_1)
    list_2 = create_service_contact_list(service=service_2)

    response = admin_request.get(
        'service.get_contact_list_by_id',
        service_id=service_1.id,
        contact_list_id=list_2.id,
        _expected_status=404
    )

    assert response['message'] == "No result found"


def test_dao_delete_contact_list_by_id(mocker, admin_request, sample_service):
    mock_s3 = mocker.patch('app.service.rest.s3.remove_contact_list_from_s3')
    service_1 = create_service(service_name='Service under test')
    template_1 = create_template(service=service_1)
    expected_list = create_service_contact_list(service=service_1)
    other_list = create_service_contact_list(service=service_1)

    job_1 = create_job(template=template_1, contact_list_id=expected_list.id)
    job_2 = create_job(template=template_1, contact_list_id=other_list.id)
    job_3 = create_job(template=template_1)

    admin_request.delete(
        'service.delete_contact_list_by_id',
        service_id=service_1.id,
        contact_list_id=expected_list.id,
    )

    assert job_1.contact_list_id is None
    assert job_2.contact_list_id == other_list.id
    assert job_3.contact_list_id is None

    mock_s3.assert_called_once_with(
        expected_list.service.id,
        expected_list.id,
    )


def test_dao_delete_contact_list_when_unused(mocker, admin_request, sample_service):
    mock_s3 = mocker.patch('app.service.rest.s3.remove_contact_list_from_s3')
    service = create_service(service_name='Service under test')
    expected_list = create_service_contact_list(service=service)

    assert ServiceContactList.query.count() == 1

    admin_request.delete(
        'service.delete_contact_list_by_id',
        service_id=service.id,
        contact_list_id=expected_list.id
    )

    assert ServiceContactList.query.count() == 0

    mock_s3.assert_called_once_with(
        expected_list.service.id,
        expected_list.id,
    )


def test_dao_delete_contact_list_by_id_for_different_service(mocker, admin_request, sample_service):

    mock_s3 = mocker.patch('app.service.rest.s3.remove_contact_list_from_s3')

    service_1 = create_service(service_name='Service under test')
    service_2 = create_service(service_name='Other service')

    contact_list = create_service_contact_list(service=service_1)
    assert ServiceContactList.query.count() == 1

    admin_request.delete(
        'service.delete_contact_list_by_id',
        service_id=service_2.id,
        contact_list_id=contact_list.id,
        _expected_status=404,
    )

    assert ServiceContactList.query.count() == 1
    assert mock_s3.called is False
