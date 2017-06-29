import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import asc, func
from sqlalchemy.orm import joinedload
from flask import current_app

from app import db
from app.dao.dao_utils import (
    transactional,
    version_class
)
from app.dao.notifications_dao import get_financial_year
from app.models import (
    NotificationStatistics,
    TemplateStatistics,
    ProviderStatistics,
    VerifyCode,
    ApiKey,
    Template,
    TemplateHistory,
    TemplateRedacted,
    Job,
    NotificationHistory,
    Notification,
    Permission,
    User,
    InvitedUser,
    Service,
    ServicePermission,
    KEY_TYPE_TEST,
    NOTIFICATION_STATUS_TYPES,
    TEMPLATE_TYPES,
    JobStatistics,
    SMS_TYPE,
    EMAIL_TYPE,
    INTERNATIONAL_SMS_TYPE,
    LETTER_TYPE
)
from app.service.statistics import format_monthly_template_notification_stats
from app.statsd_decorators import statsd
from app.utils import get_london_month_from_utc_column, get_london_midnight_in_utc


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


def dao_fetch_services_by_sms_sender(sms_sender):
    return Service.query.filter(
        Service.sms_sender == sms_sender
    ).all()


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
def dao_create_service(service, user, service_id=None, service_permissions=[SMS_TYPE, EMAIL_TYPE]):
    # the default property does not appear to work when there is a difference between the sqlalchemy schema and the
    # db schema (ie: during a migration), so we have to set sms_sender manually here. After the GOVUK sms_sender
    # migration is completed, this code should be able to be removed.
    if not service.sms_sender:
        service.sms_sender = current_app.config['FROM_NUMBER']

    from app.dao.permissions_dao import permission_dao
    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = service_id or uuid.uuid4()  # must be set now so version history model can use same id
    service.active = True
    service.research_mode = False

    def deprecate_process_service_permissions():
        for permission in service_permissions:
            service_permission = ServicePermission(service_id=service.id, permission=permission)
            service.permissions.append(service_permission)

            if permission == INTERNATIONAL_SMS_TYPE:
                service.can_send_international_sms = True
            if permission == LETTER_TYPE:
                service.can_send_letters = True

    deprecate_process_service_permissions()
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

    _delete_commit(NotificationStatistics.query.filter_by(service=service))
    _delete_commit(TemplateStatistics.query.filter_by(service=service))
    _delete_commit(ProviderStatistics.query.filter_by(service=service))
    _delete_commit(InvitedUser.query.filter_by(service=service))
    _delete_commit(Permission.query.filter_by(service=service))
    _delete_commit(ApiKey.query.filter_by(service=service))
    _delete_commit(ApiKey.get_history_model().query.filter_by(service_id=service.id))
    _delete_commit(Job.query.filter_by(service=service))
    _delete_commit(NotificationHistory.query.filter_by(service=service))
    _delete_commit(Notification.query.filter_by(service=service))
    _delete_commit(Template.query.filter_by(service=service))
    _delete_commit(TemplateHistory.query.filter_by(service_id=service.id))
    _delete_commit(ServicePermission.query.filter_by(service_id=service.id))

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
        # see dao_fetch_todays_stats_for_all_services for why we have this label
        Notification.status.label('status'),
        func.count(Notification.id).label('count')
    ).filter(
        Notification.service_id == service_id,
        Notification.key_type != KEY_TYPE_TEST
    ).group_by(
        Notification.notification_type,
        Notification.status,
    )


@statsd(namespace="dao")
def dao_fetch_monthly_historical_stats_by_template_for_service(service_id, year):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)

    start_date, end_date = get_financial_year(year)
    sq = db.session.query(
        NotificationHistory.template_id,
        # see dao_fetch_todays_stats_for_all_services for why we have this label
        NotificationHistory.status.label('status'),
        month.label('month'),
        func.count().label('count')
    ).filter(
        NotificationHistory.service_id == service_id,
        NotificationHistory.created_at.between(start_date, end_date)
    ).group_by(
        month,
        NotificationHistory.template_id,
        NotificationHistory.status
    ).subquery()

    rows = db.session.query(
        Template.id.label('template_id'),
        Template.name,
        Template.template_type,
        sq.c.status.label('status'),
        sq.c.count.label('count'),
        sq.c.month
    ).join(
        sq,
        sq.c.template_id == Template.id
    ).all()

    return format_monthly_template_notification_stats(year, rows)


@statsd(namespace="dao")
def dao_fetch_monthly_historical_stats_for_service(service_id, year):
    month = get_london_month_from_utc_column(NotificationHistory.created_at)

    start_date, end_date = get_financial_year(year)
    rows = db.session.query(
        NotificationHistory.notification_type,
        # see dao_fetch_todays_stats_for_all_services for why we have this label
        NotificationHistory.status.label('status'),
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
        datetime.strftime(date, '%Y-%m'): {
            template_type: dict.fromkeys(
                NOTIFICATION_STATUS_TYPES,
                0
            )
            for template_type in TEMPLATE_TYPES
        }
        for date in [
            datetime(year, month, 1) for month in range(4, 13)
        ] + [
            datetime(year + 1, month, 1) for month in range(1, 4)
        ]
    }

    for notification_type, status, date, count in rows:
        months[datetime.strftime(date, "%Y-%m")][notification_type][status] = count

    return months


@statsd(namespace='dao')
def dao_fetch_todays_stats_for_all_services(include_from_test_key=True):
    query = db.session.query(
        Notification.notification_type,
        # this label is necessary as the column has a different name under the hood (_status_enum / _status_fkey),
        # if we query the Notification object there is a hybrid property to translate, but here there isn't anything.
        Notification.status.label('status'),
        Notification.service_id,
        func.count(Notification.id).label('count')
    ).filter(
        func.date(Notification.created_at) == date.today()
    ).group_by(
        Notification.notification_type,
        Notification.status,
        Notification.service_id
    ).order_by(
        Notification.service_id
    )

    if not include_from_test_key:
        query = query.filter(Notification.key_type != KEY_TYPE_TEST)

    return query.all()


@statsd(namespace='dao')
def fetch_stats_by_date_range_for_all_services(start_date, end_date, include_from_test_key=True):
    start_date = get_london_midnight_in_utc(start_date)
    end_date = get_london_midnight_in_utc(end_date + timedelta(days=1))
    table = NotificationHistory

    if start_date >= datetime.utcnow() - timedelta(days=7):
        table = Notification

    query = db.session.query(
        table.notification_type,
        # see dao_fetch_todays_stats_for_all_services for why we have this label
        table.status.label('status'),
        table.service_id,
        func.count(table.id).label('count')
    ).filter(
        table.created_at >= start_date,
        table.created_at < end_date
    ).group_by(
        table.notification_type,
        table.status,
        table.service_id
    ).order_by(
        table.service_id
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
