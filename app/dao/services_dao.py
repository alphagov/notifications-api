import uuid
from datetime import date, datetime

from sqlalchemy import asc, func
from sqlalchemy.orm import joinedload

from app import db
from app.dao.dao_utils import (
    transactional,
    version_class
)
from app.models import (
    NotificationStatistics,
    TemplateStatistics,
    ProviderStatistics,
    VerifyCode,
    ApiKey,
    Template,
    TemplateHistory,
    Job,
    NotificationHistory,
    Notification,
    Permission,
    User,
    InvitedUser,
    Service,
    KEY_TYPE_TEST)
from app.statsd_decorators import statsd


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
def dao_deactive_service(service_id):
    # have to eager load templates and api keys so that we don't flush when we loop through them
    # to ensure that db.session still contains the models when it comes to creating history objects
    service = Service.query.options(
        joinedload('templates'),
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
def dao_create_service(service, user, service_id=None):
    from app.dao.permissions_dao import permission_dao
    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = service_id or uuid.uuid4()  # must be set now so version history model can use same id
    service.active = True
    service.research_mode = False
    db.session.add(service)


@transactional
@version_class(Service)
def dao_update_service(service):
    db.session.add(service)


def dao_add_user_to_service(service, user, permissions=[]):
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
        query.delete()
        db.session.commit()

    _delete_commit(NotificationStatistics.query.filter_by(service=service))
    _delete_commit(TemplateStatistics.query.filter_by(service=service))
    _delete_commit(ProviderStatistics.query.filter_by(service=service))
    _delete_commit(InvitedUser.query.filter_by(service=service))
    _delete_commit(Permission.query.filter_by(service=service))
    _delete_commit(ApiKey.query.filter_by(service=service))
    _delete_commit(ApiKey.get_history_model().query.filter_by(service_id=service.id))
    _delete_commit(NotificationHistory.query.filter_by(service=service))
    _delete_commit(Notification.query.filter_by(service=service))
    _delete_commit(Job.query.filter_by(service=service))
    _delete_commit(Template.query.filter_by(service=service))
    _delete_commit(TemplateHistory.query.filter_by(service_id=service.id))

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
def dao_fetch_weekly_historical_stats_for_service(service_id):
    monday_of_notification_week = func.date_trunc('week', NotificationHistory.created_at).label('week_start')
    return db.session.query(
        NotificationHistory.notification_type,
        NotificationHistory.status,
        monday_of_notification_week,
        func.count(NotificationHistory.id).label('count')
    ).filter(
        NotificationHistory.service_id == service_id
    ).group_by(
        NotificationHistory.notification_type,
        NotificationHistory.status,
        monday_of_notification_week
    ).order_by(
        asc(monday_of_notification_week), NotificationHistory.status
    ).all()


@statsd(namespace='dao')
def dao_fetch_todays_stats_for_all_services(include_from_test_key=True):
    query = db.session.query(
        Notification.notification_type,
        Notification.status,
        Notification.service_id,
        func.count(Notification.id).label('count')
    ).select_from(
        Service
    ).join(
        Notification
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
    query = db.session.query(
        NotificationHistory.notification_type,
        NotificationHistory.status,
        NotificationHistory.service_id,
        func.count(NotificationHistory.id).label('count')
    ).select_from(
        Service
    ).join(
        NotificationHistory
    ).filter(
        func.date(NotificationHistory.created_at) >= start_date,
        func.date(NotificationHistory.created_at) <= end_date
    ).group_by(
        NotificationHistory.notification_type,
        NotificationHistory.status,
        NotificationHistory.service_id
    ).order_by(
        NotificationHistory.service_id
    )

    if not include_from_test_key:
        query = query.filter(NotificationHistory.key_type != KEY_TYPE_TEST)

    return query.all()
