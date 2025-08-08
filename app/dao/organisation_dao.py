from flask import current_app
from sqlalchemy.sql.expression import func

from app import db
from app.constants import CAN_ASK_TO_JOIN_SERVICE, NHS_ORGANISATION_TYPES
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.dao.email_branding_dao import dao_get_email_branding_by_id
from app.dao.letter_branding_dao import dao_get_letter_branding_by_id
from app.dao.organisation_user_permissions_dao import organisation_user_permissions_dao
from app.models import (
    Domain,
    EmailBranding,
    Organisation,
    OrganisationPermission,
    OrganisationUserPermissions,
    Service,
    User,
)
from app.utils import escape_special_characters, get_archived_db_column_value


def dao_get_organisations():
    return Organisation.query.order_by(Organisation.active.desc(), Organisation.name.asc()).all()


def dao_count_organisations_with_live_services():
    return (
        db.session.query(Organisation.id)
        .join(Organisation.services)
        .filter(
            Service.active.is_(True),
            Service.restricted.is_(False),
            Service.count_as_live.is_(True),
        )
        .distinct()
        .count()
    )


def dao_get_organisation_services(organisation_id):
    return Organisation.query.filter_by(id=organisation_id).one().services


def dao_get_organisation_by_id(organisation_id):
    return Organisation.query.filter_by(id=organisation_id).one()


def dao_get_organisation_by_email_address(email_address):
    email_address = email_address.lower().replace(".gsi.gov.uk", ".gov.uk")

    for domain in Domain.query.order_by(func.char_length(Domain.domain).desc()).all():
        if email_address.endswith((f"@{domain.domain}", f".{domain.domain}")):
            return Organisation.query.filter_by(id=domain.organisation_id).one()

    return None


def dao_get_organisations_by_partial_name(organisation_name):
    organisation_name = escape_special_characters(organisation_name)
    return (
        Organisation.query.filter(Organisation.name.ilike(f"%{organisation_name}%")).order_by(Organisation.name).all()
    )


def dao_get_organisation_by_service_id(service_id):
    return Organisation.query.join(Organisation.services).filter_by(id=service_id).first()


@autocommit
def dao_create_organisation(organisation):
    if organisation.organisation_type in NHS_ORGANISATION_TYPES:
        organisation.email_branding_id = current_app.config["NHS_EMAIL_BRANDING_ID"]
        organisation.letter_branding_id = current_app.config["NHS_LETTER_BRANDING_ID"]

    join_a_service_permission = OrganisationPermission(
        organisation_id=organisation.id, permission=CAN_ASK_TO_JOIN_SERVICE
    )
    organisation.permissions.append(join_a_service_permission)

    db.session.add(organisation)
    db.session.commit()

    if organisation.organisation_type in NHS_ORGANISATION_TYPES:
        dao_add_email_branding_to_organisation_pool(organisation.id, organisation.email_branding_id)
        dao_add_letter_branding_list_to_organisation_pool(organisation.id, [organisation.letter_branding_id])


@autocommit
def dao_update_organisation(organisation_id, **kwargs):
    domains = kwargs.pop("domains", None)

    num_updated = Organisation.query.filter_by(id=organisation_id).update(kwargs)

    if isinstance(domains, list):
        Domain.query.filter_by(organisation_id=organisation_id).delete()

        db.session.bulk_save_objects(
            [Domain(domain=domain.lower(), organisation_id=organisation_id) for domain in domains]
        )

    organisation = Organisation.query.get(organisation_id)

    if "organisation_type" in kwargs:
        _update_organisation_services(organisation, "organisation_type", only_where_none=False)
        _update_organisation_services_free_allowance(organisation)

    if "crown" in kwargs:
        _update_organisation_services(organisation, "crown", only_where_none=False)

    if "email_branding_id" in kwargs:
        _update_organisation_services(organisation, "email_branding")

    if "letter_branding_id" in kwargs:
        _update_organisation_services(organisation, "letter_branding")

    _add_branding_to_branding_pool(organisation_id, kwargs)

    return num_updated


def _add_branding_to_branding_pool(organisation_id, kwargs):
    if kwargs.get("organisation_type") in NHS_ORGANISATION_TYPES:
        # If we're setting the organisation_type to one of the NHS types we always want to add the NHS branding to the
        # pool. This should happen regardless of whether we're changing the branding for the org.
        dao_add_email_branding_to_organisation_pool(
            organisation_id, current_app.config["NHS_EMAIL_BRANDING_ID"], _autocommit=False
        )
        dao_add_letter_branding_list_to_organisation_pool(
            organisation_id,
            [current_app.config["NHS_LETTER_BRANDING_ID"]],
            _autocommit=False,
        )
    else:
        if kwargs.get("email_branding_id"):
            dao_add_email_branding_to_organisation_pool(organisation_id, kwargs["email_branding_id"], _autocommit=False)

        if kwargs.get("letter_branding_id"):
            dao_add_letter_branding_list_to_organisation_pool(
                organisation_id, [kwargs["letter_branding_id"]], _autocommit=False
            )


@version_class(
    VersionOptions(Service, must_write_history=False),
)
def _update_organisation_services(organisation, attribute, only_where_none=True):
    for service in organisation.services:
        if getattr(service, attribute) is None or not only_where_none:
            setattr(service, attribute, getattr(organisation, attribute))
        db.session.add(service)


def _update_organisation_services_free_allowance(organisation):
    for service in organisation.services:
        set_default_free_allowance_for_service(service, year_start=None, _autocommit=False)


@autocommit
def dao_archive_organisation(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)

    organisation.email_branding = None
    organisation.letter_branding = None

    Domain.query.filter_by(organisation_id=organisation_id).delete()

    organisation.name = get_archived_db_column_value(organisation.name)
    organisation.active = False

    db.session.add(organisation)


@autocommit
@version_class(Service)
def dao_add_service_to_organisation(service, organisation_id):
    organisation = Organisation.query.filter_by(id=organisation_id).one()

    service.organisation_id = organisation_id
    service.organisation_type = organisation.organisation_type
    service.crown = organisation.crown

    db.session.add(service)


def dao_get_users_for_organisation(organisation_id):
    return (
        db.session.query(User)
        .join(User.organisations)
        .filter(Organisation.id == organisation_id, User.state == "active")
        .order_by(User.created_at)
        .all()
    )


@autocommit
def dao_add_user_to_organisation(organisation_id, user_id, permissions: list[str]):
    organisation = dao_get_organisation_by_id(organisation_id)
    user = User.query.filter_by(id=user_id).one()
    user.organisations.append(organisation)

    new_permissions = [
        OrganisationUserPermissions(
            user=user,
            organisation=organisation,
            permission=p,
        )
        for p in permissions
    ]
    organisation_user_permissions_dao.set_user_organisation_permission(user, organisation, new_permissions)

    db.session.add(organisation)
    return user


@autocommit
def dao_remove_user_from_organisation(organisation, user):
    organisation.users.remove(user)
    organisation_user_permissions_dao.remove_user_organisation_permissions(user, organisation)


@autocommit
def dao_add_email_branding_to_organisation_pool(organisation_id, email_branding_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    email_branding = EmailBranding.query.filter_by(id=email_branding_id).one()

    if email_branding not in organisation.email_branding_pool:
        organisation.email_branding_pool.append(email_branding)
        db.session.add(organisation)

    return email_branding


@autocommit
def dao_add_email_branding_list_to_organisation_pool(organisation_id, email_branding_ids):
    organisation = dao_get_organisation_by_id(organisation_id)
    email_brandings = [dao_get_email_branding_by_id(branding_id) for branding_id in email_branding_ids]

    organisation.email_branding_pool.extend(email_brandings)


def dao_get_email_branding_pool_for_organisation(organisation_id):
    return (
        db.session.query(EmailBranding)
        .join(EmailBranding.organisations)
        .filter(
            Organisation.id == organisation_id,
        )
        .order_by(EmailBranding.name)
        .all()
    )


def dao_get_all_organisations_with_specific_email_branding_in_their_pool(email_branding_id):
    return (
        db.session.query(Organisation)
        .join(Organisation.email_branding_pool)
        .filter(
            EmailBranding.id == email_branding_id,
        )
        .all()
    )


@autocommit
def dao_remove_email_branding_from_organisation_pool(organisation_id, email_branding_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    email_branding = EmailBranding.query.filter_by(id=email_branding_id).one()

    if organisation.email_branding_id == email_branding_id:
        from app.errors import InvalidRequest

        raise InvalidRequest("You cannot remove an organisation's default email branding", status_code=400)

    organisation.email_branding_pool.remove(email_branding)
    db.session.add(organisation)
    return email_branding


def dao_get_letter_branding_pool_for_organisation(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)

    return sorted(organisation.letter_branding_pool, key=lambda x: x.name)


@autocommit
def dao_add_letter_branding_list_to_organisation_pool(organisation_id, letter_branding_ids):
    organisation = dao_get_organisation_by_id(organisation_id)
    existing_branding_ids = {b.id for b in organisation.letter_branding_pool}

    for branding_id in letter_branding_ids:
        if branding_id not in existing_branding_ids:
            branding = dao_get_letter_branding_by_id(branding_id)
            organisation.letter_branding_pool.append(branding)
    db.session.add(organisation)


@autocommit
def dao_remove_letter_branding_from_organisation_pool(organisation_id, letter_branding_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    letter_branding = dao_get_letter_branding_by_id(letter_branding_id)

    organisation.letter_branding_pool.remove(letter_branding)

    return letter_branding
