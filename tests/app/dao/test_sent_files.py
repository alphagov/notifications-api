import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.sent_files import dao_create_sent_files
from app.models import SentFiles


def test_dao_create_sent_files(sample_email_template, sample_service):
    document_id = uuid.uuid4()
    notification_id = uuid.uuid4()
    dao_create_sent_files(document_id, "example.pdf", notification_id, sample_service.id)
    sent_file = SentFiles.query.filter(
        SentFiles.document_id == document_id,
        SentFiles.filename == "example.pdf",
        SentFiles.notification_id == notification_id,
        SentFiles.service_id == sample_service.id,
    ).all()[0]
    assert sent_file.document_id == document_id
    assert sent_file.filename == "example.pdf"
    assert sent_file.notification_id == notification_id
    assert sent_file.service_id == sample_service.id


def test_dao_create_sent_files_fails_foreign_key_violation(sample_email_template, sample_service):
    document_id = uuid.uuid4()
    notification_id = uuid.uuid4()
    service_id = uuid.uuid4()  # violates fk constraint
    with pytest.raises(IntegrityError) as e:
        dao_create_sent_files(document_id, "example.pdf", notification_id, service_id)
    assert 'insert or update on table "sent_files" violates foreign key' in str(e)
