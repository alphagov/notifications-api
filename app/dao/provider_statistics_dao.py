from sqlalchemy import func

from app import db
from app.models import (
    NotificationHistory,
    SMS_TYPE,
    EMAIL_TYPE,
    NOTIFICATION_STATUS_TYPES_BILLABLE,
    KEY_TYPE_TEST
)
from app.dao.notifications_dao import get_financial_year


def get_fragment_count(service_id, year=None):
    shared_filters = [
        NotificationHistory.service_id == service_id,
        NotificationHistory.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE),
        NotificationHistory.key_type != KEY_TYPE_TEST
    ]

    if year:
        shared_filters.append(NotificationHistory.created_at.between(
            *get_financial_year(year)
        ))

    sms_count = db.session.query(
        func.sum(NotificationHistory.billable_units)
    ).filter(
        NotificationHistory.notification_type == SMS_TYPE,
        *shared_filters
    )

    email_count = db.session.query(
        func.count(NotificationHistory.id)
    ).filter(
        NotificationHistory.notification_type == EMAIL_TYPE,
        *shared_filters
    )
    return {
        'sms_count': int(sms_count.scalar() or 0),
        'email_count': email_count.scalar() or 0
    }
