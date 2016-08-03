from sqlalchemy import func, cast, Float, case

from app import db
from app.models import (
    ProviderStatistics,
    ProviderDetails,
    NotificationHistory,
    SMS_TYPE,
    EMAIL_TYPE,
    NOTIFICATION_STATUS_TYPES_BILLABLE,
    KEY_TYPE_TEST
    )


def get_provider_statistics(service, **kwargs):
    query = ProviderStatistics.query.filter_by(service=service)
    if 'providers' in kwargs:
        providers = ProviderDetails.query.filter(ProviderDetails.identifier.in_(kwargs['providers'])).all()
        provider_ids = [provider.id for provider in providers]
        query = query.filter(ProviderStatistics.provider_id.in_(provider_ids))
    return query


def get_fragment_count(service_id):
    shared_filters = [
        NotificationHistory.service_id == service_id,
        NotificationHistory.status.in_(NOTIFICATION_STATUS_TYPES_BILLABLE),
        NotificationHistory.key_type != KEY_TYPE_TEST
    ]

    sms_count = db.session.query(
        func.sum(
            case(
                [
                    (
                        NotificationHistory.content_char_count <= 160,
                        func.ceil(cast(NotificationHistory.content_char_count, Float) / 153)
                    )
                ],
                else_=1
            )
        )
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
