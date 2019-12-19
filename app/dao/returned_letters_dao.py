from datetime import datetime

from sqlalchemy import func, desc
from sqlalchemy.dialects.postgresql import insert

from app import db
from app.dao.dao_utils import transactional
from app.models import (
    Job,
    Notification,
    NotificationHistory,
    ReturnedLetter,
    Template,
    User,
)


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
    for row in data:
        table = ReturnedLetter.__table__

        stmt = insert(table).values(
            reported_at=datetime.utcnow().date(),
            service_id=row.service_id,
            notification_id=row.id,
            created_at=datetime.utcnow()
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=[table.c.notification_id],
            set_={
                'reported_at': datetime.utcnow().date(),
                'updated_at': datetime.utcnow()
            }
        )
        db.session.connection().execute(stmt)


def fetch_returned_letter_summary(service_id):
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


def fetch_returned_letters(service_id, report_date):
    results = []
    for table in [Notification, NotificationHistory]:
        query = db.session.query(
            ReturnedLetter.notification_id,
            ReturnedLetter.reported_at,
            table.client_reference,
            table.created_at,
            Template.name.label('template_name'),
            table.template_id,
            table.template_version,
            table.created_by_id,
            User.name.label('user_name'),
            User.email_address,
            Job.original_file_name,
            (table.job_row_number + 1).label('job_row_number')  # row numbers start at 0
        ).outerjoin(
            User, table.created_by_id == User.id
        ).outerjoin(
            Job, table.job_id == Job.id
        ).filter(
            ReturnedLetter.service_id == service_id,
            ReturnedLetter.reported_at == report_date,
            ReturnedLetter.notification_id == table.id,
            table.template_id == Template.id
        ).order_by(
            desc(ReturnedLetter.reported_at), desc(table.created_at)
        )
        results = results + query.all()
    results = sorted(results, key=lambda i: i.created_at, reverse=True)
    return results
