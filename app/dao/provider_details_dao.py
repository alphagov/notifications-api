from datetime import datetime

from notifications_utils.timezones import convert_utc_to_bst
from sqlalchemy import asc, desc, func

from app.dao.dao_utils import transactional
from app.provider_details.switch_providers import (
    provider_is_inactive,
    provider_is_primary,
    switch_providers
)
from app.models import FactBilling, ProviderDetails, ProviderDetailsHistory, SMS_TYPE, User
from app import db


def get_provider_details_by_id(provider_details_id):
    return ProviderDetails.query.get(provider_details_id)


def get_provider_details_by_identifier(identifier):
    return ProviderDetails.query.filter_by(identifier=identifier).one()


def get_alternative_sms_provider(identifier):
    if identifier == 'firetext':
        return 'mmg'
    elif identifier == 'mmg':
        return 'firetext'
    raise ValueError('Unrecognised sms provider {}'.format(identifier))


def dao_get_provider_versions(provider_id):
    return ProviderDetailsHistory.query.filter_by(
        id=provider_id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).all()


@transactional
def dao_reduce_sms_provider_priority(identifier):
    # get current priority of both providers
    q = ProviderDetails.query.filter(
        ProviderDetails.notification_type == 'sms',
        ProviderDetails.active
    ).with_for_update()

    providers = {provider.identifier: provider for provider in q}
    other = get_alternative_sms_provider(identifier)

    # always keep values between 0 and 100
    providers[identifier].priority = max(0, providers[identifier].priority - 10)
    providers[other].priority = min(100, providers[other].priority + 10)

def get_provider_details_by_notification_type(notification_type, supports_international=False):

    filters = [ProviderDetails.notification_type == notification_type]

    if supports_international:
        filters.append(ProviderDetails.supports_international == supports_international)

    return ProviderDetails.query.filter(*filters).order_by(asc(ProviderDetails.priority)).all()


@transactional
def dao_update_provider_details(provider_details):
    provider_details.version += 1
    provider_details.updated_at = datetime.utcnow()
    history = ProviderDetailsHistory.from_original(provider_details)
    db.session.add(provider_details)
    db.session.add(history)


def dao_get_provider_stats():
    # this query does not include the current day since the task to populate ft_billing runs overnight

    current_bst_datetime = convert_utc_to_bst(datetime.utcnow())
    first_day_of_the_month = current_bst_datetime.date().replace(day=1)

    subquery = db.session.query(
        FactBilling.provider,
        func.sum(FactBilling.billable_units * FactBilling.rate_multiplier).label('current_month_billable_sms')
    ).filter(
        FactBilling.notification_type == SMS_TYPE,
        FactBilling.bst_date >= first_day_of_the_month
    ).group_by(
        FactBilling.provider
    ).subquery()

    result = db.session.query(
        ProviderDetails.id,
        ProviderDetails.display_name,
        ProviderDetails.identifier,
        ProviderDetails.priority,
        ProviderDetails.notification_type,
        ProviderDetails.active,
        ProviderDetails.updated_at,
        ProviderDetails.supports_international,
        User.name.label('created_by_name'),
        func.coalesce(subquery.c.current_month_billable_sms, 0).label('current_month_billable_sms')
    ).outerjoin(
        subquery, ProviderDetails.identifier == subquery.c.provider
    ).outerjoin(
        User, ProviderDetails.created_by_id == User.id
    ).order_by(
        ProviderDetails.notification_type,
        ProviderDetails.priority,
    ).all()

    return result
