import uuid

from app.models import ServiceContactList
from tests.app.db import create_service_contact_list, create_service


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
