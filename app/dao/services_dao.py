import uuid
from datetime import date, datetime, timedelta

from notifications_utils.statsd_decorators import statsd
from sqlalchemy import asc, func
from sqlalchemy.orm import joinedload
from flask import current_app

from app import db
from app.dao.dao_utils import (
    transactional,
    version_class
)
from app.dao.email_branding_dao import dao_get_email_branding_by_name
from app.dao.letter_branding_dao import dao_get_letter_branding_by_name
from app.dao.organisation_dao import dao_get_organisation_by_email_address
from app.dao.service_sms_sender_dao import insert_service_sms_sender
from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import dao_get_valid_template_folders_by_id
from app.models import (
    AnnualBilling,
    ApiKey,
    InboundNumber,
    InvitedUser,
    Job,
    Notification,
    NotificationHistory,
    Permission,
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
    SMS_TYPE,
    LETTER_TYPE,
)
from app.utils import email_address_is_nhs, get_london_midnight_in_utc, midnight_n_days_ago

DEFAULT_SERVICE_PERMISSIONS = [
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
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


def dao_count_live_services():
    return Service.query.filter_by(
        active=True,
        restricted=False,
        count_as_live=True,
    ).count()


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
def dao_create_service(
    service,
    user,
    service_id=None,
    service_permissions=None,
):
    # the default property does not appear to work when there is a difference between the sqlalchemy schema and the
    # db schema (ie: during a migration), so we have to set sms_sender manually here. After the GOVUK sms_sender
    # migration is completed, this code should be able to be removed.

    if not user:
        raise ValueError("Can't create a service without a user")

    if service_permissions is None:
        service_permissions = DEFAULT_SERVICE_PERMISSIONS

    organisation = dao_get_organisation_by_email_address(user.email_address)

    from app.dao.permissions_dao import permission_dao
    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = service_id or uuid.uuid4()  # must be set now so version history model can use same id
    service.active = True
    service.research_mode = False
    service.crown = service.organisation_type == 'central'
    service.count_as_live = not user.platform_admin

    for permission in service_permissions:
        service_permission = ServicePermission(service_id=service.id, permission=permission)
        service.permissions.append(service_permission)

    # do we just add the default - or will we get a value from FE?
    insert_service_sms_sender(service, current_app.config['FROM_NUMBER'])

    if organisation:

        service.organisation = organisation

        if organisation.email_branding:
            service.email_branding = organisation.email_branding

        if organisation.letter_branding and not service.letter_branding:
            service.letter_branding = organisation.letter_branding

    elif service.organisation_type == 'nhs' or email_address_is_nhs(user.email_address):

        service.email_branding = dao_get_email_branding_by_name('NHS')
        service.letter_branding = dao_get_letter_branding_by_name('NHS')

    db.session.add(service)


@transactional
@version_class(Service)
def dao_update_service(service):
    db.session.add(service)


def dao_add_user_to_service(service, user, permissions=None, folder_permissions=None):
    permissions = permissions or []
    folder_permissions = folder_permissions or []

    try:
        from app.dao.permissions_dao import permission_dao
        service.users.append(user)
        permission_dao.set_user_service_permission(user, service, permissions, _commit=False)
        db.session.add(service)

        service_user = dao_get_service_user(user.id, service.id)
        valid_template_folders = dao_get_valid_template_folders_by_id(folder_permissions)
        service_user.folders = valid_template_folders
        db.session.add(service_user)

    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def dao_remove_user_from_service(service, user):
    try:
        from app.dao.permissions_dao import permission_dao
        permission_dao.remove_user_service_permissions(user, service)

        service_user = dao_get_service_user(user.id, service.id)
        db.session.delete(service_user)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def delete_service_and_all_associated_db_objects(service):

    def _delete_commit(query):
        query.delete(synchronize_session=False)
        db.session.commit()

    subq = db.session.query(Template.id).filter_by(service=service).subquery()
    _delete_commit(TemplateRedacted.query.filter(TemplateRedacted.template_id.in_(subq)))

    _delete_commit(ServiceSmsSender.query.filter_by(service=service))
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
def dao_fetch_stats_for_service(service_id, limit_days):
    # We always want between seven and eight days
    start_date = midnight_n_days_ago(limit_days)
    return _stats_for_service_query(service_id).filter(
        Notification.created_at >= start_date
    ).all()


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


@statsd(namespace='dao')
def dao_fetch_todays_stats_for_all_services(include_from_test_key=True, only_active=True):
    today = date.today()
    start_date = get_london_midnight_in_utc(today)
    end_date = get_london_midnight_in_utc(today + timedelta(days=1))

    subquery = db.session.query(
        Notification.notification_type,
        Notification.status,
        Notification.service_id,
        func.count(Notification.id).label('count')
    ).filter(
        Notification.created_at >= start_date,
        Notification.created_at < end_date
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
        User.services.any(id=service_id),
        User.state == 'active'
    )

    return query.all()
