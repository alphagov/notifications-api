from datetime import datetime

from sqlalchemy import func, desc
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.dao.dao_utils import transactional
from app.models import Notification, NotificationHistory, ReturnedLetter


def _get_notification_ids_for_references(references):
    notification_ids = db.session.query(Notification.id, Notification.service_id).filter(
        Notification.reference.in_(references)
    ).all()

    notification_history_ids = db.session.query(NotificationHistory.id, NotificationHistory.service_id).filter(
        NotificationHistory.reference.in_(references)
    ).all()

    return notification_ids + notification_history_ids


@transactional
def insert_or_update_returned_letters(references):
    data = _get_notification_ids_for_references(references)
    now = datetime.utcnow()
    for row in data:
        table = ReturnedLetter.__table__

        stmt = insert(table).values(
            reported_at=now,
            service_id=row.service_id,
            notification_id=row.id)

        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.notification_id],
            set_={
                'reported_at': now,
            }
        )
        db.session.connection().execute(stmt)


def get_returned_letter_summary(service_id):
    return db.session.query(
        func.count(ReturnedLetter.notification_id).label('returned_letter_count'),
        ReturnedLetter.reported_at
    ).filter(
        ReturnedLetter.service_id == service_id,
    ).group_by(
        ReturnedLetter.reported_at
    ).order_by(
        desc(ReturnedLetter.reported_at)
    ).all()
