from app import db
from app.dao.dao_utils import autocommit
from app.models import SentFiles


@autocommit
def dao_create_sent_files(document_id, filename, notification_id, service_id):
    sent_files = SentFiles(
        document_id=document_id, filename=filename, notification_id=notification_id, service_id=service_id
    )
    db.session.add(sent_files)
