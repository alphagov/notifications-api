import uuid
from datetime import UTC, datetime, timedelta

import pytest
from freezegun import freeze_time

from app.models import ServiceContactList
from tests.app.db import (
    create_job,
    create_service,
    create_service_contact_list,
    create_service_data_retention,
    create_template,
)


def test_create_service_contact_list(sample_service, admin_request):
    data = {
        "id": str(uuid.uuid4()),
        "row_count": 100,
        "original_file_name": "staff_emergency_list.xls",
        "template_type": "email",
        "created_by": str(sample_service.users[0].id),
    }

    response = admin_request.post(
        "service.create_contact_list", _data=data, service_id=sample_service.id, _expected_status=201
    )

    assert response["id"] == data["id"]
    assert response["original_file_name"] == "staff_emergency_list.xls"
    assert response["row_count"] == 100
    assert response["template_type"] == "email"
    assert response["service_id"] == str(sample_service.id)
    assert response["created_at"]

    db_results = ServiceContactList.query.all()
    assert len(db_results) == 1
    assert str(db_results[0].id) == data["id"]


def test_create_service_contact_list_cannot_save_type_letter(sample_service, admin_request):
    data = {
        "id": str(uuid.uuid4()),
        "row_count": 100,
        "original_file_name": "staff_emergency_list.xls",
        "template_type": "letter",
        "created_by": str(sample_service.users[0].id),
    }

    response = admin_request.post(
        "service.create_contact_list", _data=data, service_id=sample_service.id, _expected_status=400
    )
    assert response["errors"][0]["message"] == "template_type letter is not one of [email, sms]"


@freeze_time("2020-06-06 12:00")
def test_get_contact_list(admin_request, notify_db_session):
    contact_list = create_service_contact_list()

    response = admin_request.get("service.get_contact_list", service_id=contact_list.service_id)

    assert len(response) == 1
    assert response[0] == contact_list.serialize()
    assert response[0]["recent_job_count"] == 0
    assert response[0]["created_at"] == "2020-06-06T12:00:00.000000Z"


@pytest.mark.parametrize(
    "days_of_email_retention, expected_job_count",
    (
        (None, 8),
        (7, 8),
        (3, 4),
    ),
)
def test_get_contact_list_counts_jobs(
    sample_template,
    admin_request,
    days_of_email_retention,
    expected_job_count,
):
    if days_of_email_retention:
        create_service_data_retention(sample_template.service, "email", days_of_email_retention)

    # This should be ignored because it’s another template type
    create_service_data_retention(sample_template.service, "sms", 1)

    contact_list_1 = create_service_contact_list(service=sample_template.service)
    contact_list_2 = create_service_contact_list(service=sample_template.service)

    for i in range(10):
        create_job(
            template=sample_template,
            contact_list_id=contact_list_2.id,
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=i),
        )

    response = admin_request.get("service.get_contact_list", service_id=contact_list_1.service_id)

    assert len(response) == 2

    assert response[0]["id"] == str(contact_list_2.id)
    assert response[0]["recent_job_count"] == expected_job_count
    assert response[0]["has_jobs"] is True

    assert response[1]["id"] == str(contact_list_1.id)
    assert response[1]["recent_job_count"] == 0
    assert response[1]["has_jobs"] is False


def test_get_contact_list_returns_for_service(admin_request, notify_db_session):
    service_1 = create_service(service_name="Service under test")
    service_2 = create_service(service_name="Service should return results")

    expected_list_1 = create_service_contact_list(service=service_1)
    expected_list_2 = create_service_contact_list(service=service_1)
    # not included in results
    create_service_contact_list(service=service_2)
    create_service_contact_list(service=service_1, archived=True)

    response = admin_request.get("service.get_contact_list", service_id=service_1.id)

    assert len(response) == 2
    assert response[0] == expected_list_2.serialize()
    assert response[1] == expected_list_1.serialize()


def test_dao_get_contact_list_by_id(admin_request, sample_service):
    service_1 = create_service(service_name="Service under test")

    expected_list_1 = create_service_contact_list(service=service_1)
    create_service_contact_list(service=service_1)

    response = admin_request.get(
        "service.get_contact_list_by_id", service_id=service_1.id, contact_list_id=expected_list_1.id
    )

    assert response == expected_list_1.serialize()


def test_dao_get_archived_contact_list_by_id(admin_request):
    contact_list = create_service_contact_list(archived=True)
    admin_request.get(
        "service.get_contact_list_by_id",
        service_id=contact_list.service.id,
        contact_list_id=contact_list.id,
        _expected_status=404,
    )


def test_dao_get_contact_list_by_id_does_not_return_if_contact_list_id_for_another_service(
    admin_request, sample_service
):
    service_1 = create_service(service_name="Service requesting list")
    service_2 = create_service(service_name="Service that owns the list")

    create_service_contact_list(service=service_1)
    list_2 = create_service_contact_list(service=service_2)

    response = admin_request.get(
        "service.get_contact_list_by_id", service_id=service_1.id, contact_list_id=list_2.id, _expected_status=404
    )

    assert response["message"] == "No result found"


def test_archive_contact_list_by_id(mocker, admin_request, sample_service):
    mock_s3 = mocker.patch("app.service.rest.s3.remove_contact_list_from_s3")
    service_1 = create_service(service_name="Service under test")
    template_1 = create_template(service=service_1)
    expected_list = create_service_contact_list(service=service_1)
    other_list = create_service_contact_list(service=service_1)

    # Job linked to the contact list we’re deleting
    job_1 = create_job(template=template_1, contact_list_id=expected_list.id)
    # Other jobs and lists shouldn’t be affected
    job_2 = create_job(template=template_1, contact_list_id=other_list.id)
    job_3 = create_job(template=template_1)

    admin_request.delete(
        "service.delete_contact_list_by_id",
        service_id=service_1.id,
        contact_list_id=expected_list.id,
    )

    assert job_1.contact_list_id == expected_list.id
    assert expected_list.archived is True

    assert job_2.contact_list_id == other_list.id
    assert other_list.archived is False

    assert job_3.contact_list_id is None

    mock_s3.assert_called_once_with(
        expected_list.service.id,
        expected_list.id,
    )


def test_archive_contact_list_when_unused(mocker, admin_request, sample_service):
    mock_s3 = mocker.patch("app.service.rest.s3.remove_contact_list_from_s3")
    service = create_service(service_name="Service under test")
    expected_list = create_service_contact_list(service=service)

    assert ServiceContactList.query.count() == 1

    admin_request.delete("service.delete_contact_list_by_id", service_id=service.id, contact_list_id=expected_list.id)

    assert ServiceContactList.query.count() == 1
    assert expected_list.archived is True

    mock_s3.assert_called_once_with(
        expected_list.service.id,
        expected_list.id,
    )


def test_archive_contact_list_by_id_for_different_service(mocker, admin_request, sample_service):
    mock_s3 = mocker.patch("app.service.rest.s3.remove_contact_list_from_s3")

    service_1 = create_service(service_name="Service under test")
    service_2 = create_service(service_name="Other service")

    contact_list = create_service_contact_list(service=service_1)
    assert ServiceContactList.query.count() == 1

    admin_request.delete(
        "service.delete_contact_list_by_id",
        service_id=service_2.id,
        contact_list_id=contact_list.id,
        _expected_status=404,
    )

    assert ServiceContactList.query.count() == 1
    assert mock_s3.called is False
