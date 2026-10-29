from app import db
from app.dao.dao_utils import autocommit
from app.models import SentFiles


@autocommit
def dao_create_sent_files(document_id, placeholder, notification_id, service_id):
    sent_files = SentFiles(
        document_id=document_id, placeholder=placeholder, notification_id=notification_id, service_id=service_id
    )
    db.session.add(sent_files)


@autocommit
def dao_get_sent_files_by_notification_id_and_placeholder(notification_id, placeholder):
    return SentFiles.query.filter(
        SentFiles.notification_id == notification_id, SentFiles.placeholder == placeholder
    ).all()
