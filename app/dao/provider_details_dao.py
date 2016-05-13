from sqlalchemy import asc
from app.dao.dao_utils import transactional
from app.models import ProviderDetails
from app import db


def get_provider_details():
    return ProviderDetails.query.order_by(asc(ProviderDetails.priority), asc(ProviderDetails.notification_type)).all()


def get_provider_details_by_id(provider_details_id):
    return ProviderDetails.query.get(provider_details_id)


def get_provider_details_by_notification_type(notification_type):
    return ProviderDetails.query.filter_by(
        notification_type=notification_type
    ).order_by(asc(ProviderDetails.priority)).all()


@transactional
def dao_update_provider_details(provider_details):
    db.session.add(provider_details)
