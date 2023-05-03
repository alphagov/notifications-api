import uuid

from app.dao.templates_dao import dao_get_template_by_id
from app.models import LetterAttachment
from tests.app.db import create_letter_attachment, create_user


def test_get_letter_attachment_by_id_returns_correct_object(admin_request, notify_db_session):
    user = create_user()
    attachment = create_letter_attachment(created_by_id=user.id)

    response = admin_request.get(
        "letter_attachment.get_letter_attachment", _expected_status=200, letter_attachment_id=attachment.id
    )

    assert response["created_by_id"] == str(user.id)


def test_get_letter_attachment_by_id_returns_404_if_uuid_doesnt_exist(admin_request, notify_db_session):
    admin_request.get(
        "letter_attachment.get_letter_attachment", _expected_status=404, letter_attachment_id=uuid.uuid4()
    )


def test_create_letter_attachment_creates_a_db_entry_and_adds_attachment_id_to_template(
    admin_request, notify_db_session, sample_letter_template
):
    data = {
        "upload_id": str(uuid.uuid4()),
        "created_by_id": str(sample_letter_template.created_by_id),
        "original_filename": "securely_attached.pdf",
        "page_count": 2,
        "template_id": str(sample_letter_template.id),
    }

    response = admin_request.post("letter_attachment.create_letter_attachment", _data=data, _expected_status=201)

    letter_attachments = LetterAttachment.query.all()

    assert len(letter_attachments) == 1

    assert response["id"] == data["upload_id"]
    assert response["created_by_id"] == data["created_by_id"]
    assert response["original_filename"] == data["original_filename"]
    assert response["page_count"] == 2

    template = dao_get_template_by_id(sample_letter_template.id)

    assert str(template.letter_attachment_id) == data["upload_id"]


def test_create_letter_attachment_creates_new_version_of_template_history(admin_request, sample_letter_template):
    assert sample_letter_template.version == 1

    upload_id = uuid.uuid4()

    admin_request.post(
        "letter_attachment.create_letter_attachment",
        _data={
            "upload_id": str(upload_id),
            "created_by_id": str(sample_letter_template.created_by_id),
            "original_filename": "filename.pdf",
            "page_count": 2,
            "template_id": str(sample_letter_template.id),
        },
        _expected_status=201,
    )

    original_version = dao_get_template_by_id(sample_letter_template.id, version=1)
    new_version = dao_get_template_by_id(sample_letter_template.id, version=2)
    assert original_version.version == 1
    assert original_version.letter_attachment_id is None
    assert new_version.version == 2
    assert new_version.letter_attachment_id == upload_id
    # make sure we didn't add a third version
    assert sample_letter_template.version == 2


def test_create_letter_attachment_returns_404_if_template_id_doesnt_exist(admin_request, sample_letter_template):
    data = {
        "upload_id": str(uuid.uuid4()),
        "created_by_id": str(sample_letter_template.created_by_id),
        "original_filename": "securely_attached.pdf",
        "page_count": 2,
        "template_id": str(uuid.uuid4()),
    }

    admin_request.post("letter_attachment.create_letter_attachment", _data=data, _expected_status=404)


def test_create_letter_attachment_returns_400_if_template_already_has_attachment(
    admin_request, notify_db_session, sample_letter_template
):
    attachment = create_letter_attachment(created_by_id=sample_letter_template.created_by_id)
    sample_letter_template.letter_attachment_id = attachment.id

    data = {
        "upload_id": str(uuid.uuid4()),
        "created_by_id": str(sample_letter_template.created_by_id),
        "original_filename": "securely_attached.pdf",
        "page_count": 2,
        "template_id": str(sample_letter_template.id),
    }

    admin_request.post("letter_attachment.create_letter_attachment", _data=data, _expected_status=400)


def test_archive_letter_attachment_creates_new_template_version(
    admin_request, notify_db_session, sample_letter_template
):
    assert sample_letter_template.version == 1

    upload_id = uuid.uuid4()

    response = admin_request.post(
        "letter_attachment.create_letter_attachment",
        _data={
            "upload_id": str(upload_id),
            "created_by_id": str(sample_letter_template.created_by_id),
            "original_filename": "filename.pdf",
            "page_count": 2,
            "template_id": str(sample_letter_template.id),
        },
        _expected_status=201,
    )

    user = create_user()
    data = {
        "template_id": str(sample_letter_template.id),
        "archived_by": str(user.id),
    }

    admin_request.post(
        "letter_attachment.archive_letter_attachment",
        _data=data,
        letter_attachment_id=response["id"],
        _expected_status=204,
    )

    attached_version = dao_get_template_by_id(sample_letter_template.id, version=2)
    new_version = dao_get_template_by_id(sample_letter_template.id, version=3)

    assert attached_version.version == 2
    assert new_version.version == 3
    assert new_version.letter_attachment_id is None
    # make sure we didn't add a third version
    assert sample_letter_template.version == 3


def test_archive_letter_attachment_updates_db(admin_request, notify_db_session, sample_letter_template):
    assert sample_letter_template.version == 1

    upload_id = uuid.uuid4()

    response = admin_request.post(
        "letter_attachment.create_letter_attachment",
        _data={
            "upload_id": str(upload_id),
            "created_by_id": str(sample_letter_template.created_by_id),
            "original_filename": "filename.pdf",
            "page_count": 2,
            "template_id": str(sample_letter_template.id),
        },
        _expected_status=201,
    )

    user = create_user()
    data = {
        "archived_by": str(user.id),
    }

    admin_request.post(
        "letter_attachment.archive_letter_attachment",
        _data=data,
        letter_attachment_id=response["id"],
        _expected_status=204,
    )

    letter_attachment = LetterAttachment.query.one()
    assert letter_attachment.archived_by_id == user.id
    assert letter_attachment.archived_at is not None


def test_archive_letter_attachment_returns_404_if_template_id_doesnt_exist(admin_request, sample_letter_template):
    upload_id = uuid.uuid4()
    response = admin_request.post(
        "letter_attachment.create_letter_attachment",
        _data={
            "upload_id": str(upload_id),
            "created_by_id": str(sample_letter_template.created_by_id),
            "original_filename": "filename.pdf",
            "page_count": 2,
            "template_id": str(sample_letter_template.id),
        },
        _expected_status=201,
    )
    user = create_user()
    attachment = dao_get_template_by_id(sample_letter_template.id).letter_attachment
    attachment.template = None
    data = {
        "archived_by": str(user.id),
    }
    admin_request.post(
        "letter_attachment.archive_letter_attachment",
        _data=data,
        letter_attachment_id=response["id"],
        _expected_status=400,
    )


def test_archive_letter_attachment_returns_404_if_attachment_doesnt_exist(admin_request, sample_letter_template):
    random_uuid = uuid.uuid4()

    data = {
        "archived_by": str(random_uuid),
    }
    admin_request.post(
        "letter_attachment.archive_letter_attachment",
        _data=data,
        letter_attachment_id=random_uuid,
        _expected_status=404,
    )
