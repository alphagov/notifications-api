from datetime import datetime

from app import db
from app.dao.dao_utils import autocommit
from app.models import ServiceDataRetention


def fetch_service_data_retention_by_id(service_id, data_retention_id):
    data_retention = ServiceDataRetention.query.filter_by(service_id=service_id, id=data_retention_id).first()
    return data_retention


def fetch_service_data_retention(service_id):
    data_retention_list = ServiceDataRetention.query.filter_by(
        service_id=service_id
    ).order_by(
        # in the order that models.notification_types are created (email, sms, letter)
        ServiceDataRetention.notification_type
    ).all()
    return data_retention_list


def fetch_service_data_retention_by_notification_type(service_id, notification_type):
    data_retention_list = ServiceDataRetention.query.filter_by(
        service_id=service_id,
        notification_type=notification_type
    ).first()
    return data_retention_list


@autocommit
def insert_service_data_retention(service_id, notification_type, days_of_retention):
    new_data_retention = ServiceDataRetention(service_id=service_id,
                                              notification_type=notification_type,
                                              days_of_retention=days_of_retention)

    db.session.add(new_data_retention)
    return new_data_retention


@autocommit
def update_service_data_retention(service_data_retention_id, service_id, days_of_retention):
    updated_count = ServiceDataRetention.query.filter(
        ServiceDataRetention.id == service_data_retention_id,
        ServiceDataRetention.service_id == service_id
    ).update(
        {
            "days_of_retention": days_of_retention,
            "updated_at": datetime.utcnow()
        }
    )
    return updated_count
