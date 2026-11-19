from app import db
from app.dao.dao_utils import autocommit
from app.models import SentFiles


@autocommit
def dao_create_sent_files(document_id, placeholder, notification_id, service_id, filename=None):
    sent_files = SentFiles(
        document_id=document_id,
        placeholder=placeholder,
        notification_id=notification_id,
        service_id=service_id,
        filename=filename,
    )
    db.session.add(sent_files)
