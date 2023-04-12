import uuid

from app.dao.templates_dao import dao_get_template_by_id


def test_get_letter_attachment_by_id_returns_object():
    pass


def test_get_letter_attachment_by_id_returns_404_if_uuid_doesnt_exist():
    pass


def test_create_letter_attachment_creates_object():
    pass


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


def test_create_letter_attachment_returns_404_if_template_id_doesnt_exist():
    pass


def test_create_letter_attachment_returns_400_if_template_already_has_attachment():
    pass
