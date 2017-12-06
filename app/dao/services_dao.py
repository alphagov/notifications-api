import uuid
from datetime import date, datetime, timedelta, time

from sqlalchemy import asc, func, extract
from sqlalchemy.orm import joinedload
from flask import current_app

from app import db
from app.dao.dao_utils import (
    transactional,
    version_class
)
from app.dao.date_util import get_financial_year
from app.dao.service_sms_sender_dao import insert_service_sms_sender
from app.dao.stats_template_usage_by_month_dao import dao_get_template_usage_stats_by_service
from app.models import (
    AnnualBilling,
    ApiKey,
    InboundNumber,
    InvitedUser,
    Job,
    JobStatistics,
    Notification,
    NotificationHistory,
    Permission,
    ProviderStatistics,
    Service,
    ServicePermission,
    ServiceSmsSender,
    Template,
    TemplateHistory,
    TemplateRedacted,
    User,
    VerifyCode,
    EMAIL_TYPE,
    INTERNATIONAL_SMS_TYPE,
    KEY_TYPE_TEST,
    NOTIFICATION_STATUS_TYPES,
    SMS_TYPE,
    TEMPLATE_TYPES
)
from app.statsd_decorators import statsd
from app.utils import get_london_month_from_utc_column, get_london_midnight_in_utc

DEFAULT_SERVICE_PERMISSIONS = [
    SMS_TYPE,
    EMAIL_TYPE,
    INTERNATIONAL_SMS_TYPE,
]


def dao_fetch_all_services(only_active=False):
    query = Service.query.order_by(
        asc(Service.created_at)
    ).options(
        joinedload('users')
    )

    if only_active:
        query = query.filter(Service.active)

    return query.all()


def dao_fetch_service_by_id(service_id, only_active=False):
    query = Service.query.filter_by(
        id=service_id
    ).options(
        joinedload('users')
    )

    if only_active:
        query = query.filter(Service.active)

    return query.one()


def dao_fetch_service_by_inbound_number(number):
    inbound_number = InboundNumber.query.filter(
        InboundNumber.number == number,
        InboundNumber.active
    ).first()

    if not inbound_number:
        return None

    return Service.query.filter(
        Service.id == inbound_number.service_id
    ).first()


def dao_fetch_service_by_id_with_api_keys(service_id, only_active=False):
    query = Service.query.filter_by(
        id=service_id
    ).options(
        joinedload('api_keys')
    )

    if only_active:
        query = query.filter(Service.active)

    return query.one()


def dao_fetch_all_services_by_user(user_id, only_active=False):
    query = Service.query.filter(
        Service.users.any(id=user_id)
    ).order_by(
        asc(Service.created_at)
    ).options(
        joinedload('users')
    )

    if only_active:
        query = query.filter(Service.active)

    return query.all()


@transactional
@version_class(Service)
@version_class(Template, TemplateHistory)
@version_class(ApiKey)
def dao_archive_service(service_id):
    # have to eager load templates and api keys so that we don't flush when we loop through them
    # to ensure that db.session still contains the models when it comes to creating history objects
    service = Service.query.options(
        joinedload('templates'),
        joinedload('templates.template_redacted'),
        joinedload('api_keys'),
    ).filter(Service.id == service_id).one()

    service.active = False
    service.name = '_archived_' + service.name
    service.email_from = '_archived_' + service.email_from

    for template in service.templates:
        if not template.archived:
            template.archived = True

    for api_key in service.api_keys:
        if not api_key.expiry_date:
            api_key.expiry_date = datetime.utcnow()


def dao_fetch_service_by_id_and_user(service_id, user_id):
    return Service.query.filter(
        Service.users.any(id=user_id),
        Service.id == service_id
    ).options(
        joinedload('users')
    ).one()


@transactional
@version_class(Service)
def dao_create_service(service, user, service_id=None, service_permissions=None):
    # the default property does not appear to work when there is a difference between the sqlalchemy schema and the
    # db schema (ie: during a migration), so we have to set sms_sender manually here. After the GOVUK sms_sender
    # migration is completed, this code should be able to be removed.

    if service_permissions is None:
        service_permissions = DEFAULT_SERVICE_PERMISSIONS

    from app.dao.permissions_dao import permission_dao
    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = service_id or uuid.uuid4()  # must be set now so version history model can use same id
    service.active = True
    service.research_mode = False
    service.crown = service.organisation_type == 'central'

    for permission in service_permissions:
        service_permission = ServicePermission(service_id=service.id, permission=permission)
        service.permissions.append(service_permission)

    # do we just add the default - or will we get a value from FE?
    insert_service_sms_sender(service, current_app.config['FROM_NUMBER'])
    db.session.add(service)


@transactional
@version_class(Service)
def dao_update_service(service):
    db.session.add(service)


def dao_add_user_to_service(service, user, permissions=None):
    permissions = permissions or []
    try:
        from app.dao.permissions_dao import permission_dao
        service.users.append(user)
        permission_dao.set_user_service_permission(user, service, permissions, _commit=False)
        db.session.add(service)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def dao_remove_user_from_service(service, user):
    try:
        from app.dao.permissions_dao import permission_dao
        permission_dao.remove_user_service_permissions(user, service)
        service.users.remove(user)
        db.session.add(service)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def delete_service_and_all_associated_db_objects(service):

    def _delete_commit(query):
        query.delete(synchronize_session=False)
        db.session.commit()

    job_stats = JobStatistics.query.join(Job).filter(Job.service_id == service.id)
    list(map(db.session.delete, job_stats))
    db.session.commit()

    subq = db.session.query(Template.id).filter_by(service=service).subquery()
    _delete_commit(TemplateRedacted.query.filter(TemplateRedacted.template_id.in_(subq)))

    _delete_commit(ServiceSmsSender.query.filter_by(service=service))
    _delete_commit(ProviderStatistics.query.filter_by(service=service))
    _delete_commit(InvitedUser.query.filter_by(service=service))
    _delete_commit(Permission.query.filter_by(service=service))
    _delete_commit(NotificationHistory.query.filter_by(service=service))
    _delete_commit(Notification.query.filter_by(service=service))
    _delete_commit(Job.query.filter_by(service=service))
    _delete_commit(Template.query.filter_by(service=service))
    _delete_commit(TemplateHistory.query.filter_by(service_id=service.id))
    _delete_commit(ServicePermission.query.filter_by(service_id=service.id))
    _delete_commit(ApiKey.query.filter_by(service=service))
    _delete_commit(ApiKey.get_history_model().query.filter_by(service_id=service.id))
    _delete_commit(AnnualBilling.query.filter_by(service_id=service.id))

    verify_codes = VerifyCode.query.join(User).filter(User.id.in_([x.id for x in service.users]))
    list(map(db.session.delete, verify_codes))
    db.session.commit()
    users = [x for x in service.users]
    map(service.users.remove, users)
    [service.users.remove(x) for x in users]
    _delete_commit(Service.get_history_model().query.filter_by(id=service.id))
    db.session.delete(service)
    db.session.commit()
    list(map(db.session.delete, users))
    db.session.commit()


@statsd(namespace="dao")
def dao_fetch_stats_for_service(service_id):
    return _stats_for_service_query(service_id).all()


@statsd(namespace="dao")
def dao_fetch_todays_stats_for_service(service_id):
    return _stats_for_service_query(service_id).filter(
        func.date(Notification.created_at) == date.today()
    ).all()


def fetch_todays_total_message_count(service_id):
    result = db.session.query(
        func.count(Notification.id).label('count')
    ).filter(
        Notification.service_id == service_id,
        Notification.key_type != KEY_TYPE_TEST,
        func.date(Notification.created_at) == date.today()
    ).group_by(
        Notification.notification_type,
        Notification.status,
    ).first()
    return 0 if result is None else result.count


def _stats_for_service_query(service_id):
    return db.session.query(
        Notification.notification_type,
        Notification.status,
        func.count(Notification.id).label('count')
    ).filter(
        Notification.service_id == service_id,
        Notification.key_type != KEY_TYPE_TEST
    ).group_by(
        Notification.notification_type,
        Notification.status,
    )


@statsd(namespace="dao")
def dao_fetch_monthly_historical_stats_for_service(service_id, year):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)

    start_date, end_date = get_financial_year(year)
    rows = db.session.query(
        NotificationHistory.notification_type,
        NotificationHistory.status,
        month,
        func.count(NotificationHistory.id).label('count')
    ).filter(
        NotificationHistory.service_id == service_id,
        NotificationHistory.created_at.between(start_date, end_date)
    ).group_by(
        NotificationHistory.notification_type,
        NotificationHistory.status,
        month
    ).order_by(
        month
    )

    months = {
        datetime.strftime(created_date, '%Y-%m'): {
            template_type: dict.fromkeys(
                NOTIFICATION_STATUS_TYPES,
                0
            )
            for template_type in TEMPLATE_TYPES
        }
        for created_date in [
            datetime(year, month, 1) for month in range(4, 13)
        ] + [
            datetime(year + 1, month, 1) for month in range(1, 4)
        ]
    }

    for notification_type, status, created_date, count in rows:
        months[datetime.strftime(created_date, "%Y-%m")][notification_type][status] = count

    return months


@statsd(namespace='dao')
def dao_fetch_todays_stats_for_all_services(include_from_test_key=True, only_active=True):

    subquery = db.session.query(
        Notification.notification_type,
        Notification.status,
        Notification.service_id,
        func.count(Notification.id).label('count')
    ).filter(
        func.date(Notification.created_at) == date.today(),
    ).group_by(
        Notification.notification_type,
        Notification.status,
        Notification.service_id
    )

    if not include_from_test_key:
        subquery = subquery.filter(Notification.key_type != KEY_TYPE_TEST)

    subquery = subquery.subquery()

    query = db.session.query(
        Service.id.label('service_id'),
        Service.name,
        Service.restricted,
        Service.research_mode,
        Service.active,
        Service.created_at,
        subquery.c.notification_type,
        subquery.c.status,
        subquery.c.count
    ).outerjoin(
        subquery,
        subquery.c.service_id == Service.id
    ).order_by(Service.id)

    if only_active:
        query = query.filter(Service.active)

    return query.all()


@statsd(namespace='dao')
def fetch_stats_by_date_range_for_all_services(start_date, end_date, include_from_test_key=True, only_active=True):
    start_date = get_london_midnight_in_utc(start_date)
    end_date = get_london_midnight_in_utc(end_date + timedelta(days=1))
    table = NotificationHistory

    if start_date >= datetime.utcnow() - timedelta(days=7):
        table = Notification
    subquery = db.session.query(
        table.notification_type,
        table.status,
        table.service_id,
        func.count(table.id).label('count')
    ).filter(
        table.created_at >= start_date,
        table.created_at < end_date
    ).group_by(
        table.notification_type,
        table.status,
        table.service_id
    )
    if not include_from_test_key:
        subquery = subquery.filter(table.key_type != KEY_TYPE_TEST)
    subquery = subquery.subquery()

    query = db.session.query(
        Service.id.label('service_id'),
        Service.name,
        Service.restricted,
        Service.research_mode,
        Service.active,
        Service.created_at,
        subquery.c.notification_type,
        subquery.c.status,
        subquery.c.count
    ).outerjoin(
        subquery,
        subquery.c.service_id == Service.id
    ).order_by(Service.id)
    if only_active:
        query = query.filter(Service.active)

    return query.all()


@statsd(namespace='dao')
def fetch_aggregate_stats_by_date_range_for_all_services(start_date, end_date, include_from_test_key=True):
    start_date = get_london_midnight_in_utc(start_date)
    end_date = get_london_midnight_in_utc(end_date + timedelta(days=1))
    table = NotificationHistory

    if start_date >= datetime.utcnow() - timedelta(days=7):
        table = Notification

    query = db.session.query(
        table.notification_type,
        table.status,
        func.count(table.id).label('count')
    ).filter(
        table.created_at >= start_date,
        table.created_at < end_date
    ).group_by(
        table.notification_type,
        table.status
    ).order_by(
        table.notification_type
    )

    if not include_from_test_key:
        query = query.filter(table.key_type != KEY_TYPE_TEST)

    return query.all()


@transactional
@version_class(Service)
@version_class(ApiKey)
def dao_suspend_service(service_id):
    # have to eager load api keys so that we don't flush when we loop through them
    # to ensure that db.session still contains the models when it comes to creating history objects
    service = Service.query.options(
        joinedload('api_keys'),
    ).filter(Service.id == service_id).one()

    service.active = False

    for api_key in service.api_keys:
        if not api_key.expiry_date:
            api_key.expiry_date = datetime.utcnow()


@transactional
@version_class(Service)
def dao_resume_service(service_id):
    service = Service.query.get(service_id)
    service.active = True


def dao_fetch_active_users_for_service(service_id):
    query = User.query.filter(
        User.user_to_service.any(id=service_id),
        User.state == 'active'
    )

    return query.all()


@statsd(namespace="dao")
def dao_fetch_monthly_historical_stats_by_template():
    month = get_london_month_from_utc_column(NotificationHistory.created_at)
    year = func.date_trunc("year", NotificationHistory.created_at)
    end_date = datetime.combine(date.today(), time.min)

    return db.session.query(
        NotificationHistory.template_id,
        extract('month', month).label('month'),
        extract('year', year).label('year'),
        func.count().label('count')
    ).filter(
        NotificationHistory.created_at < end_date
    ).group_by(
        NotificationHistory.template_id,
        month,
        year
    ).order_by(
        year,
        month
    ).all()


@statsd(namespace="dao")
def dao_fetch_monthly_historical_usage_by_template_for_service(service_id, year):

    results = dao_get_template_usage_stats_by_service(service_id, year)

    stats = []
    for result in results:
        stat = type("", (), {})()
        stat.template_id = result.template_id
        stat.template_type = result.template_type
        stat.name = str(result.name)
        stat.month = result.month
        stat.year = result.year
        stat.count = result.count
        stats.append(stat)

    month = get_london_month_from_utc_column(Notification.created_at)
    year_func = func.date_trunc("year", Notification.created_at)
    start_date = datetime.combine(date.today(), time.min)

    fy_start, fy_end = get_financial_year(year)

    if fy_start < datetime.now() < fy_end:
        today_results = db.session.query(
            Notification.template_id,
            Template.name,
            Template.template_type,
            extract('month', month).label('month'),
            extract('year', year_func).label('year'),
            func.count().label('count')
        ).join(
            Template, Notification.template_id == Template.id,
        ).filter(
            Notification.created_at >= start_date,
            Notification.service_id == service_id
        ).group_by(
            Notification.template_id,
            Template.name,
            Template.template_type,
            month,
            year_func
        ).order_by(
            Notification.template_id
        ).all()

        for today_result in today_results:
            add_to_stats = True
            for stat in stats:
                if today_result.template_id == stat.template_id and today_result.month == stat.month \
                        and today_result.year == stat.year:
                    stat.count = stat.count + today_result.count
                    add_to_stats = False

            if add_to_stats:
                new_stat = type("", (), {})()
                new_stat.template_id = today_result.template_id
                new_stat.template_type = today_result.template_type
                new_stat.name = today_result.name
                new_stat.month = int(today_result.month)
                new_stat.year = int(today_result.year)
                new_stat.count = today_result.count
                stats.append(new_stat)

    return stats
