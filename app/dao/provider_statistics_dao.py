from sqlalchemy import func
from app import db
from app.models import (ProviderStatistics, SMS_PROVIDERS, EMAIL_PROVIDERS)


def get_provider_statistics(service, **kwargs):
    return filter_query(ProviderStatistics.query, service, **kwargs)


def get_fragment_count(service, date_from, date_to):
    sms_query = filter_query(
        ProviderStatistics.query,
        service,
        providers=SMS_PROVIDERS,
        date_from=date_from,
        date_to=date_to
    )
    email_query = filter_query(
        ProviderStatistics.query,
        service,
        providers=EMAIL_PROVIDERS,
        date_from=date_from,
        date_to=date_to
    )
    return {
        'sms_count': int(sms_query.with_entities(
            func.sum(ProviderStatistics.unit_count)).scalar()) if sms_query.count() > 0 else 0,
        'email_count': int(email_query.with_entities(
            func.sum(ProviderStatistics.unit_count)).scalar()) if email_query.count() > 0 else 0
    }


def filter_query(query, service, **kwargs):
    query = query.filter_by(service=service)
    if 'providers' in kwargs:
        query = query.filter(ProviderStatistics.provider.in_(kwargs['providers']))
    if 'date_from' in kwargs:
        query.filter(ProviderStatistics.day >= kwargs['date_from'])
    if 'date_to' in kwargs:
        query.filter(ProviderStatistics.day <= kwargs['date_to'])
    return query
