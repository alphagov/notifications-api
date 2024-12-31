from datetime import date, datetime, timedelta

from flask import current_app
from sqlalchemy import Float, cast
from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import and_, asc, case, func

from app import db
from app.constants import (
    CROWN_ORGANISATION_TYPES,
    EMAIL_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NHS_ORGANISATION_TYPES,
    NON_CROWN_ORGANISATION_TYPES,
    NOTIFICATION_PERMANENT_FAILURE,
    SMS_TYPE,
    UPLOAD_LETTERS,
)
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.dao.date_util import get_current_financial_year
from app.dao.email_branding_dao import dao_get_email_branding_by_name
from app.dao.letter_branding_dao import dao_get_letter_branding_by_name
from app.dao.organisation_dao import dao_get_organisation_by_email_address
from app.dao.service_sms_sender_dao import insert_service_sms_sender
from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import dao_get_valid_template_folders_by_id
from app.models import (
    AnnualBilling,
    ApiKey,
    FactBilling,
    InboundNumber,
    InboundSms,
    InboundSmsHistory,
    InvitedUser,
    Job,
    Notification,
    NotificationHistory,
    Organisation,
    Permission,
    Service,
    ServiceContactList,
    ServiceEmailReplyTo,
    ServiceInboundApi,
    ServiceLetterContact,
    ServicePermission,
    ServiceSmsSender,
    Template,
    TemplateHistory,
    TemplateRedacted,
    User,
    VerifyCode,
)
from app.utils import (
    email_address_is_nhs,
    escape_special_characters,
    get_archived_db_column_value,
    get_london_midnight_in_utc,
)

DEFAULT_SERVICE_PERMISSIONS = [
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    INTERNATIONAL_SMS_TYPE,
    UPLOAD_LETTERS,
    INTERNATIONAL_LETTERS,
]


def dao_fetch_all_services(only_active=False):
    query = Service.query.order_by(asc(Service.created_at)).options(joinedload("users"))

    if only_active:
        query = query.filter(Service.active)

    return query.all()


def get_services_by_partial_name(service_name):
    service_name = escape_special_characters(service_name)
    return Service.query.filter(Service.name.ilike(f"%{service_name}%")).all()


def dao_count_live_services():
    return Service.query.filter_by(
        active=True,
        restricted=False,
        count_as_live=True,
    ).count()


def dao_fetch_live_services_data():
    year_start_date, year_end_date = get_current_financial_year()

    most_recent_annual_billing = (
        db.session.query(
            AnnualBilling.service_id.label("service_id"),
            AnnualBilling.free_sms_fragment_limit.label("free_sms_fragment_limit"),
            AnnualBilling.financial_year_start.label("financial_year_start"),
        )
        .distinct(AnnualBilling.service_id)
        .order_by(AnnualBilling.service_id, AnnualBilling.financial_year_start.desc())
        .subquery()
    )

    data = (
        db.session.query(
            Service.id.label("service_id"),
            Service.name.label("service_name"),
            Organisation.name.label("organisation_name"),
            Organisation.organisation_type.label("organisation_type"),
            Service.consent_to_research.label("consent_to_research"),
            User.name.label("contact_name"),
            User.email_address.label("contact_email"),
            User.mobile_number.label("contact_mobile"),
            Service.go_live_at.label("live_date"),
            Service.volume_sms.label("sms_volume_intent"),
            Service.volume_email.label("email_volume_intent"),
            Service.volume_letter.label("letter_volume_intent"),
            func.sum(case([(FactBilling.notification_type == "email", FactBilling.notifications_sent)], else_=0)).label(
                "email_totals"
            ),
            func.sum(case([(FactBilling.notification_type == "sms", FactBilling.notifications_sent)], else_=0)).label(
                "sms_totals"
            ),
            func.sum(
                case([(FactBilling.notification_type == "letter", FactBilling.notifications_sent)], else_=0)
            ).label("letter_totals"),
            most_recent_annual_billing.c.free_sms_fragment_limit,
        )
        .join(most_recent_annual_billing, Service.id == most_recent_annual_billing.c.service_id)
        .outerjoin(Organisation, Organisation.id == Service.organisation_id)
        .outerjoin(User, User.id == Service.go_live_user_id)
        .outerjoin(
            FactBilling,
            and_(
                FactBilling.service_id == Service.id,
                FactBilling.bst_date >= year_start_date,
                FactBilling.bst_date <= year_end_date,
            ),
        )
        .filter(Service.count_as_live.is_(True), Service.active.is_(True), Service.restricted.is_(False))
        .group_by(
            Service.id,
            Organisation.name,
            Organisation.organisation_type,
            Service.name,
            Service.consent_to_research,
            User.name,
            User.email_address,
            User.mobile_number,
            Service.go_live_at,
            Service.volume_sms,
            Service.volume_email,
            Service.volume_letter,
            most_recent_annual_billing.c.free_sms_fragment_limit,
        )
        .order_by(asc(Service.go_live_at))
        .all()
    )

    return [row._asdict() for row in data]


def dao_fetch_service_by_id(service_id, only_active=False, with_users=True):
    query = Service.query.filter_by(id=service_id)

    if with_users:
        query = query.options(joinedload("users"))

    if only_active:
        query = query.filter(Service.active)

    return query.one()


def dao_fetch_service_by_inbound_number(number):
    inbound_number = InboundNumber.query.filter(InboundNumber.number == number, InboundNumber.active).first()

    if not inbound_number:
        return None

    return Service.query.filter(Service.id == inbound_number.service_id).first()


def dao_fetch_service_by_id_with_api_keys(service_id, only_active=False):
    query = Service.query.filter_by(id=service_id).options(joinedload("api_keys"))

    if only_active:
        query = query.filter(Service.active)

    return query.one()


def dao_fetch_all_services_by_user(user_id, only_active=False):
    query = (
        Service.query.filter(Service.users.any(id=user_id))
        .order_by(asc(Service.created_at))
        .options(joinedload("users"))
    )

    if only_active:
        query = query.filter(Service.active)

    return query.all()


def dao_fetch_all_services_created_by_user(user_id):
    query = Service.query.filter_by(created_by_id=user_id).order_by(asc(Service.created_at))

    return query.all()


@autocommit
@version_class(
    VersionOptions(ApiKey, must_write_history=False),
    VersionOptions(Service),
    VersionOptions(Template, history_class=TemplateHistory, must_write_history=False),
)
def dao_archive_service(service_id):
    # have to eager load templates and api keys so that we don't flush when we loop through them
    # to ensure that db.session still contains the models when it comes to creating history objects
    service = (
        Service.query.options(
            joinedload("templates"),
            joinedload("templates.template_redacted"),
            joinedload("api_keys"),
        )
        .filter(Service.id == service_id)
        .one()
    )

    service.active = False
    service.name = get_archived_db_column_value(service.name)

    for template in service.templates:
        if not template.archived:
            template.archived = True

    for api_key in service.api_keys:
        if not api_key.expiry_date:
            api_key.expiry_date = datetime.utcnow()


def dao_fetch_service_by_id_and_user(service_id, user_id):
    return (
        Service.query.filter(Service.users.any(id=user_id), Service.id == service_id).options(joinedload("users")).one()
    )


@autocommit
@version_class(Service)
def dao_create_service(  # noqa: C901
    service,
    user,
    service_permissions=None,
):
    if not user:
        raise ValueError("Can't create a service without a user")

    if service_permissions is None:
        service_permissions = DEFAULT_SERVICE_PERMISSIONS

    organisation = dao_get_organisation_by_email_address(user.email_address)

    from app.dao.permissions_dao import permission_dao

    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.active = True

    for permission in service_permissions:
        service_permission = ServicePermission(service_id=service.id, permission=permission)
        service.permissions.append(service_permission)

    # do we just add the default - or will we get a value from FE?
    insert_service_sms_sender(service, current_app.config["FROM_NUMBER"])

    if organisation:
        service.organisation_id = organisation.id
        service.organisation_type = organisation.organisation_type

        if organisation.email_branding:
            service.email_branding = organisation.email_branding

        if organisation.letter_branding:
            service.letter_branding = organisation.letter_branding

    elif service.organisation_type in NHS_ORGANISATION_TYPES or email_address_is_nhs(user.email_address):
        service.email_branding = dao_get_email_branding_by_name("NHS")
        service.letter_branding = dao_get_letter_branding_by_name("NHS")

    if organisation:
        service.crown = organisation.crown
    elif service.organisation_type in CROWN_ORGANISATION_TYPES:
        service.crown = True
    elif service.organisation_type in NON_CROWN_ORGANISATION_TYPES:
        service.crown = False
    service.count_as_live = not user.platform_admin

    db.session.add(service)


@autocommit
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
    """
    To be used with functional test services only! This irrevocably deletes data, use with extreme caution!
    """

    def _delete(query):
        query.delete(synchronize_session=False)

    subq = db.session.query(Template.id).filter_by(service=service).subquery()
    _delete(TemplateRedacted.query.filter(TemplateRedacted.template_id.in_(subq)))

    _delete(InboundSms.query.filter_by(service=service))
    _delete(InboundSmsHistory.query.filter_by(service=service))
    _delete(ServiceInboundApi.query.filter_by(service=service))

    _delete(ServiceSmsSender.query.filter_by(service=service))
    _delete(InboundNumber.query.filter_by(service=service))
    _delete(ServiceEmailReplyTo.query.filter_by(service=service))
    _delete(ServiceContactList.query.filter_by(service=service))
    _delete(InvitedUser.query.filter_by(service=service))
    _delete(Permission.query.filter_by(service=service))
    _delete(NotificationHistory.query.filter_by(service=service))
    _delete(Notification.query.filter_by(service=service))
    _delete(Job.query.filter_by(service=service))
    _delete(Template.query.filter_by(service=service))
    _delete(TemplateHistory.query.filter_by(service_id=service.id))
    _delete(ServiceLetterContact.query.filter_by(service=service))
    _delete(ServicePermission.query.filter_by(service_id=service.id))
    _delete(ApiKey.query.filter_by(service=service))
    _delete(ApiKey.get_history_model().query.filter_by(service_id=service.id))
    _delete(AnnualBilling.query.filter_by(service_id=service.id))

    verify_codes = VerifyCode.query.join(User).filter(User.id.in_([x.id for x in service.users]))
    list(map(db.session.delete, verify_codes))
    users = list(service.users)
    for user in users:
        user.organisations = []
        service.users.remove(user)

    _delete(Service.get_history_model().query.filter_by(id=service.id))
    _delete(Service.query.filter_by(id=service.id))

    db.session.commit()


def dao_fetch_todays_stats_for_service(service_id):
    today = date.today()
    start_date = get_london_midnight_in_utc(today)

    return (
        db.session.query(
            Notification.notification_type, Notification.status, func.count(Notification.id).label("count")
        )
        .filter(
            Notification.service_id == service_id,
            Notification.key_type != KEY_TYPE_TEST,
            Notification.created_at >= start_date,
        )
        .group_by(
            Notification.notification_type,
            Notification.status,
        )
        .all()
    )


def dao_fetch_todays_stats_for_all_services(include_from_test_key=True, only_active=True):
    today = date.today()
    start_date = get_london_midnight_in_utc(today)
    end_date = get_london_midnight_in_utc(today + timedelta(days=1))

    subquery = (
        db.session.query(
            Notification.notification_type,
            Notification.status,
            Notification.service_id,
            func.count(Notification.id).label("count"),
        )
        .filter(Notification.created_at >= start_date, Notification.created_at < end_date)
        .group_by(Notification.notification_type, Notification.status, Notification.service_id)
    )

    if not include_from_test_key:
        subquery = subquery.filter(Notification.key_type != KEY_TYPE_TEST)

    subquery = subquery.subquery()

    query = (
        db.session.query(
            Service.id.label("service_id"),
            Service.name,
            Service.restricted,
            Service.active,
            Service.created_at,
            subquery.c.notification_type,
            subquery.c.status,
            subquery.c.count,
        )
        .outerjoin(subquery, subquery.c.service_id == Service.id)
        .order_by(Service.id)
    )

    if only_active:
        query = query.filter(Service.active)

    return query.all()


def dao_fetch_active_users_for_service(service_id):
    query = User.query.filter(User.services.any(id=service_id), User.state == "active")

    return query.all()


def dao_find_services_sending_to_tv_numbers(start_date, end_date, threshold=500):
    return (
        db.session.query(
            Notification.service_id.label("service_id"), func.count(Notification.id).label("notification_count")
        )
        .filter(
            Notification.service_id == Service.id,
            Notification.created_at >= start_date,
            Notification.created_at <= end_date,
            Notification.key_type != KEY_TYPE_TEST,
            Notification.notification_type == SMS_TYPE,
            func.substr(Notification.normalised_to, 3, 7) == "7700900",
            Service.restricted == False,  # noqa
            Service.active == True,  # noqa
        )
        .group_by(
            Notification.service_id,
        )
        .having(func.count(Notification.id) > threshold)
        .all()
    )


def dao_find_services_with_high_failure_rates(start_date, end_date, threshold=10000):
    subquery = (
        db.session.query(func.count(Notification.id).label("total_count"), Notification.service_id.label("service_id"))
        .filter(
            Notification.service_id == Service.id,
            Notification.created_at >= start_date,
            Notification.created_at <= end_date,
            Notification.key_type != KEY_TYPE_TEST,
            Notification.notification_type == SMS_TYPE,
            Service.restricted == False,  # noqa
            Service.active == True,  # noqa
        )
        .group_by(
            Notification.service_id,
        )
        .having(func.count(Notification.id) >= threshold)
    )

    subquery = subquery.subquery()

    query = (
        db.session.query(
            Notification.service_id.label("service_id"),
            func.count(Notification.id).label("permanent_failure_count"),
            subquery.c.total_count.label("total_count"),
            (cast(func.count(Notification.id), Float) / cast(subquery.c.total_count, Float)).label(
                "permanent_failure_rate"
            ),
        )
        .join(subquery, subquery.c.service_id == Notification.service_id)
        .filter(
            Notification.service_id == Service.id,
            Notification.created_at >= start_date,
            Notification.created_at <= end_date,
            Notification.key_type != KEY_TYPE_TEST,
            Notification.notification_type == SMS_TYPE,
            Notification.status == NOTIFICATION_PERMANENT_FAILURE,
            Service.restricted == False,  # noqa
            Service.active == True,  # noqa
        )
        .group_by(Notification.service_id, subquery.c.total_count)
        .having(cast(func.count(Notification.id), Float) / cast(subquery.c.total_count, Float) >= 0.25)
    )

    return query.all()


def get_live_services_with_organisation():
    query = (
        db.session.query(
            Service.id.label("service_id"),
            Service.name.label("service_name"),
            Organisation.id.label("organisation_id"),
            Organisation.name.label("organisation_name"),
        )
        .outerjoin(Service.organisation)
        .filter(Service.count_as_live.is_(True), Service.active.is_(True), Service.restricted.is_(False))
        .order_by(Organisation.name, Service.name)
    )

    return query.all()


def fetch_billing_details_for_all_services():
    return (
        db.session.query(
            Service.id.label("service_id"),
            func.coalesce(Service.purchase_order_number, Organisation.purchase_order_number).label(
                "purchase_order_number"
            ),
            func.coalesce(Service.billing_contact_names, Organisation.billing_contact_names).label(
                "billing_contact_names"
            ),
            func.coalesce(Service.billing_contact_email_addresses, Organisation.billing_contact_email_addresses).label(
                "billing_contact_email_addresses"
            ),
            func.coalesce(Service.billing_reference, Organisation.billing_reference).label("billing_reference"),
        )
        .outerjoin(Service.organisation)
        .all()
    )
