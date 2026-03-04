import uuid

import freezegun
import pytest

from app.dao.templates_dao import dao_update_template
from app.models import TemplateEmailFile, TemplateEmailFileHistory
from tests.app.db import create_template_email_file


@freezegun.freeze_time("2025-01-01 11:09:00.000000")
def test_create_template_email_file_happy_path(sample_service, sample_email_template, admin_request):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
        "pending": False,
    }
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _data=data,
        _expected_status=201,
    )

    # test response contains created email file data
    assert response["data"]["filename"] == "example.pdf"
    assert response["data"]["retention_period"] == 90
    assert response["data"]["link_text"] == "click this link!"
    assert response["data"]["validate_users_email"]
    assert response["data"]["template_id"] == str(sample_email_template.id)
    assert response["data"]["template_version"] == int(sample_email_template.version)
    assert response["data"]["created_by_id"] == str(sample_service.users[0].id)

    # test that email file gets persisted into the database
    template_email_file = TemplateEmailFile.query.get(str(response["data"]["id"]))
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.retention_period == 90
    assert template_email_file.link_text == "click this link!"
    assert template_email_file.validate_users_email
    assert template_email_file.template_id == sample_email_template.id
    assert template_email_file.template_version == int(sample_email_template.version)
    assert template_email_file.created_by_id == sample_service.users[0].id
    assert template_email_file.version == 1
    assert str(template_email_file.created_at) == "2025-01-01 11:09:00"


def test_create_template_email_file_fails_if_template_not_email_type(
    sample_service, sample_sms_template, admin_request
):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_sms_template.id,
        _data=data,
        _expected_status=400,
    )
    assert response["message"] == "Cannot add an email file to a non-email template"
    assert response["result"] == "error"


def test_create_template_email_file_fails_if_template_does_not_exist(sample_service, admin_request):
    non_existent_template_id = uuid.uuid4()
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=non_existent_template_id,
        _data=data,
        _expected_status=404,
    )
    assert response["message"] == "No result found"
    assert response["result"] == "error"


@pytest.mark.parametrize("filename", ("example.pdf", "EXAMPLE.PDF", "Exa mple.pdf"))
def test_create_template_email_file_fails_if_template_already_has_file_with_same_name(
    sample_service, admin_request, sample_email_template, sample_template_email_file_not_pending, filename
):
    data = {
        "filename": filename,
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
    }
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _data=data,
        _expected_status=400,
    )
    assert response["message"] == f"File named {filename} already exists for template id {sample_email_template.id}"
    assert response["result"] == "error"


def test_create_template_email_file_creates_file_with_latest_template_version(
    sample_service, sample_email_template, sample_template_email_file_not_pending, admin_request
):
    # template version after creating the first email file
    assert sample_template_email_file_not_pending.template_version == 2

    # updating the template
    sample_email_template.content = "here is some new content"
    dao_update_template(sample_email_template)
    assert sample_email_template.version == 3

    # create second email file
    file_two_data = {
        "filename": "example_two.pdf",
        "link_text": "here's a pdf",
        "retention_period": 30,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
        "pending": False,
    }
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _data=file_two_data,
        _expected_status=201,
    )

    # test that second email file is created with newest template version
    file_two_id = response["data"]["id"]
    file_two_fetched = TemplateEmailFile.query.get(str(file_two_id))
    assert file_two_fetched.template_version == 4


@pytest.mark.parametrize(
    "data, expected_errors",
    [
        (
            {
                "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
                "filename": "example.pdf",
                "link_text": "click this link!",
                "retention_period": "not an integer",
                "validate_users_email": True,
            },
            [{"error": "ValidationError", "message": "retention_period not an integer is not of type integer"}],
        ),
        (
            {
                "id": "d963f496-b075-4e13-90ae-1f009feddbc6",
                "filename": "example.pdf",
                "link_text": "click this link!",
                "retention_period": 90,
                "validate_users_email": "this is a string",
            },
            [{"error": "ValidationError", "message": "validate_users_email this is a string is not of type boolean"}],
        ),
    ],
)
def test_create_template_email_file_raises_exception_for_invalid_data(
    client, sample_service, sample_email_template, data, expected_errors, admin_request
):
    # default to function-scoped fixture if not set as test parameter
    if "template_id" not in data.keys():
        data["template_id"] = str(sample_email_template.id)
    if "template_version" not in data.keys():
        data["template_version"] = int(sample_email_template.version)
    if "created_by_id" not in data.keys():
        data["created_by_id"] = str(sample_service.users[0].id)
    response = admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _data=data,
        _expected_status=400,
    )
    assert response["errors"] == expected_errors


@pytest.mark.parametrize("get_pending", [True, False, None])
@pytest.mark.parametrize(
    "files",
    [
        (
            {
                "filename": "example.pdf",
                "link_text": "example.pdf",
                "retention_period": 90,
                "validate_users_email": True,
                "pending": False,
            },
        ),
        (
            {
                "filename": "example.pdf",
                "link_text": "example.pdf",
                "retention_period": 90,
                "validate_users_email": True,
                "pending": True,
            },
        ),
        (
            {
                "filename": "example.pdf",
                "link_text": "example.pdf",
                "retention_period": 90,
                "validate_users_email": True,
                "pending": False,
            },
            {
                "filename": "another example.pdf",
                "link_text": "click for an exciting pdf!",
                "retention_period": 30,
                "validate_users_email": False,
                "pending": False,
            },
        ),
        (
            {
                "filename": "example.pdf",
                "link_text": "example.pdf",
                "retention_period": 90,
                "validate_users_email": True,
                "pending": False,
            },
            {
                "filename": "another example.pdf",
                "link_text": "click for an exciting pdf!",
                "retention_period": 30,
                "validate_users_email": False,
                "pending": True,
            },
        ),
    ],
)
def test_get_template_email_files_returns_all_files(
    sample_service, sample_email_template, files, admin_request, get_pending
):
    live_file_objects = []
    for file in files:
        if not get_pending and file.get("pending", False):
            pass
        else:
            file["template_id"] = str(sample_email_template.id)
            file["created_by_id"] = str(sample_service.users[0].id)
            if not file["pending"]:
                live_file_objects += [create_template_email_file(**file)]
    if get_pending is not None:
        response = admin_request.get(
            "template_email_files.get_template_email_files",
            service_id=sample_service.id,
            template_id=sample_email_template.id,
            _expected_status=200,
            get_pending=get_pending,
        )
    else:
        response = admin_request.get(
            "template_email_files.get_template_email_files",
            service_id=sample_service.id,
            template_id=sample_email_template.id,
            _expected_status=200,
        )

    assert {str(file.id) for file in live_file_objects} == {file["id"] for file in response["data"]}
    assert {file.filename for file in live_file_objects} == {file["filename"] for file in response["data"]}
    assert {file.retention_period for file in live_file_objects} == {
        file["retention_period"] for file in response["data"]
    }
    assert {file.link_text for file in live_file_objects} == {file["link_text"] for file in response["data"]}
    assert {file.validate_users_email for file in live_file_objects} == {
        file["validate_users_email"] for file in response["data"]
    }
    assert {str(file.template_id) for file in live_file_objects} == {file["template_id"] for file in response["data"]}
    assert {file.version for file in live_file_objects} == {file["version"] for file in response["data"]}
    assert {str(file.created_by_id) for file in live_file_objects} == {
        file["created_by_id"] for file in response["data"]
    }


def test_get_template_email_file_by_id_returns_correct_file(
    sample_template_email_file_not_pending, sample_service, admin_request
):
    response = admin_request.get(
        "template_email_files.get_template_email_file_by_id",
        template_id=sample_template_email_file_not_pending.template_id,
        template_email_file_id=sample_template_email_file_not_pending.id,
        service_id=sample_service.id,
        _expected_status=200,
    )
    assert response["data"]["id"] == str(sample_template_email_file_not_pending.id)
    assert response["data"]["version"] == sample_template_email_file_not_pending.version


def test_get_template_email_file_by_id_when_file_does_not_exist_returns_404(
    sample_service, sample_email_template, admin_request, fake_uuid
):
    admin_request.get(
        "template_email_files.get_template_email_file_by_id",
        template_id=sample_email_template.id,
        template_email_file_id=fake_uuid,
        service_id=sample_service.id,
        _expected_status=404,
    )


def test_update_template_email_file(
    client, sample_service, sample_template_email_file_not_pending, sample_email_template, admin_request
):
    update_data = {
        "filename": "new_example.pdf",
        "link_text": "click this new link!",
        "retention_period": 30,
        "validate_users_email": False,
    }

    assert sample_template_email_file_not_pending.template_version == 2
    assert sample_template_email_file_not_pending.version == 1

    response = admin_request.post(
        "template_email_files.update_template_email_file",
        service_id=sample_service.id,
        template_id=sample_template_email_file_not_pending.template_id,
        template_email_file_id=sample_template_email_file_not_pending.id,
        _expected_status=200,
        _data=update_data,
    )

    # template version has been updated
    assert sample_email_template.version == 3

    # we serve updated email file in the response
    assert response["data"]["link_text"] == "click this new link!"
    assert response["data"]["retention_period"] == 30
    assert response["data"]["validate_users_email"] is False
    assert response["data"]["template_version"] == 3
    assert response["data"]["version"] == 2

    # email file updated in the database
    template_email_file = TemplateEmailFile.query.get(str(sample_template_email_file_not_pending.id))
    assert template_email_file.link_text == "click this new link!"
    assert template_email_file.retention_period == 30
    assert template_email_file.validate_users_email is False
    assert template_email_file.template_version == 3
    assert template_email_file.version == 2

    # historical email file record from before update
    template_email_file_history_version_one = TemplateEmailFileHistory.query.get(
        {"id": str(sample_template_email_file_not_pending.id), "version": 1}
    )
    assert template_email_file_history_version_one.link_text == "follow this link"
    assert template_email_file_history_version_one.retention_period == 90
    assert template_email_file_history_version_one.validate_users_email is True
    assert template_email_file_history_version_one.template_version == 2
    assert template_email_file_history_version_one.version == 1

    # historical email file record from after update
    template_email_file_history_version_two = TemplateEmailFileHistory.query.get(
        {"id": str(sample_template_email_file_not_pending.id), "version": 2}
    )
    assert template_email_file_history_version_two.link_text == "click this new link!"
    assert template_email_file_history_version_two.retention_period == 30
    assert template_email_file_history_version_two.validate_users_email is False
    assert template_email_file_history_version_two.template_version == 3
    assert template_email_file_history_version_two.version == 2


def test_archive_template_email_file(client, sample_service, sample_email_template, admin_request):
    data = {
        "filename": "example.pdf",
        "link_text": "click this link!",
        "retention_period": 90,
        "validate_users_email": True,
        "template_id": str(sample_email_template.id),
        "created_by_id": str(sample_service.users[0].id),
        "pending": False,
    }
    with freezegun.freeze_time("2025-01-01 11:09:00.000000"):
        template_email_file = create_template_email_file(**data)
    assert template_email_file.version == 1  # should be version 1 if not pending
    data = {"archived_by_id": str(sample_service.users[0].id)}
    with freezegun.freeze_time("2025-10-10 22:13:00.000000"):
        response = admin_request.post(
            "template_email_files.archive_template_email_file",
            service_id=sample_service.id,
            template_id=sample_email_template.id,
            template_email_file_id=template_email_file.id,
            _expected_status=200,
            _data=data,
        )
    assert response["data"]["archived_at"] == "2025-10-10 22:13:00"
    assert response["data"]["archived_by"] == str(sample_service.users[0].id)
    archived_file = TemplateEmailFile.query.get(template_email_file.id)
    assert str(archived_file.archived_at) == "2025-10-10 22:13:00"
    assert archived_file.archived_by.id == sample_service.users[0].id
    assert archived_file.version == 2
    file_history = TemplateEmailFileHistory.query.filter(TemplateEmailFileHistory.id == template_email_file.id).all()
    assert len(file_history) == 2


def test_multiple_pending_files_with_the_same_name_create(sample_service, sample_email_template, admin_request):
    data = {
        "filename": "example.pdf",
        "retention_period": 78,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
        "pending": True,
    }
    for _ in range(3):
        admin_request.post(
            "template_email_files.create_template_email_file",
            service_id=sample_service.id,
            template_id=sample_email_template.id,
            _data=data,
            _expected_status=201,
        )

    files = TemplateEmailFile.query.filter(TemplateEmailFile.template_id == sample_email_template.id).all()
    assert len(files) == 3
    assert all(file.filename == "example.pdf" for file in files)
    assert len({file.id for file in files}) == 3


@pytest.mark.parametrize("filename", ("example.pdf", "EXAMPLE.PDF", "Exam Ple.pdf"))
def test_make_live_fails_if_live_file_with_same_filename_exists(
    sample_service, sample_email_template, admin_request, sample_template_email_file_pending, filename
):
    # create a file with the same name as sample_template_email_file that is also called example.pdf
    data = {
        "filename": filename,
        "retention_period": 78,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
        "pending": True,
    }
    admin_request.post(
        "template_email_files.create_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        _data=data,
        _expected_status=201,
    )
    # make sample_template_email_file_live
    update_data = {"pending": False}
    admin_request.post(
        "template_email_files.update_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        template_email_file_id=sample_template_email_file_pending.id,
        _expected_status=200,
        _data=update_data,
    )
    pending_template_email_files = TemplateEmailFile.query.filter(
        TemplateEmailFile.template_id == sample_email_template.id, TemplateEmailFile.pending.is_(True)
    ).all()
    assert len(pending_template_email_files) == 1

    # try and make this file live should raise bad request error
    response = admin_request.post(
        "template_email_files.update_template_email_file",
        service_id=sample_service.id,
        template_id=pending_template_email_files[0].template_id,
        template_email_file_id=pending_template_email_files[0].id,
        _expected_status=400,
        _data=update_data,
    )
    assert response["message"] == f"File named {filename} already exists for template id {sample_email_template.id}"
    assert response["result"] == "error"


def test_create_and_make_live_file(sample_service, sample_email_template, admin_request):
    data = {
        "filename": "example.pdf",
        "retention_period": 78,
        "validate_users_email": True,
        "created_by_id": str(sample_service.users[0].id),
        "pending": True,
    }
    with freezegun.freeze_time("2025-01-01 11:09:00.000000"):
        response = admin_request.post(
            "template_email_files.create_template_email_file",
            service_id=sample_service.id,
            template_id=sample_email_template.id,
            _data=data,
            _expected_status=201,
        )

    # check created file is created correctly, and at version 0 and
    # template_version 1
    template_email_file = TemplateEmailFile.query.get(str(response["data"]["id"]))
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.retention_period == 78
    assert template_email_file.link_text is None
    assert template_email_file.template_version == 1
    assert template_email_file.version == 0
    assert template_email_file.pending
    assert str(template_email_file.created_at) == "2025-01-01 11:09:00"

    # update the files link text, without making it live
    update_data = {"link_text": "this is a file!"}
    response = admin_request.post(
        "template_email_files.update_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        template_email_file_id=template_email_file.id,
        _expected_status=200,
        _data=update_data,
    )
    # check that the link_text has been updated, but that the file version
    # and the template_version are unchanged
    assert response["data"]["link_text"] == "this is a file!"
    template_email_file = TemplateEmailFile.query.get(str(response["data"]["id"]))
    assert template_email_file.link_text == "this is a file!"
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.retention_period == 78
    assert template_email_file.version == 0
    assert template_email_file.template_version == 1
    assert template_email_file.pending

    # check that making the file live bumps the version by one and bumps the template
    # version by 1 and updates pending to False
    update_data = {"pending": False}
    response = admin_request.post(
        "template_email_files.update_template_email_file",
        service_id=sample_service.id,
        template_id=sample_email_template.id,
        template_email_file_id=template_email_file.id,
        _expected_status=200,
        _data=update_data,
    )
    template_email_file = TemplateEmailFile.query.get(str(response["data"]["id"]))
    assert template_email_file.link_text == "this is a file!"
    assert template_email_file.filename == "example.pdf"
    assert template_email_file.retention_period == 78
    assert template_email_file.version == 1
    assert template_email_file.template_version == 2
    assert not template_email_file.pending
