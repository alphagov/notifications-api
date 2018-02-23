from app import db
from app.dao.dao_utils import transactional
from app.models import (
    Organisation,
    InvitedOrganisationUser,
    User
)


def dao_get_organisations():
    return Organisation.query.order_by(
        Organisation.active.desc(), Organisation.name.asc()
    ).all()


def dao_get_organisation_services(organisation_id):
    return Organisation.query.filter_by(
        id=organisation_id
    ).one().services


def dao_get_organisation_by_id(organisation_id):
    return Organisation.query.filter_by(id=organisation_id).one()


def dao_get_organisation_by_service_id(service_id):
    return Organisation.query.join(Organisation.services).filter_by(id=service_id).first()


@transactional
def dao_create_organisation(organisation):
    db.session.add(organisation)


@transactional
def dao_update_organisation(organisation_id, **kwargs):
    return Organisation.query.filter_by(id=organisation_id).update(
        kwargs
    )


@transactional
def dao_add_service_to_organisation(service, organisation_id):
    organisation = Organisation.query.filter_by(
        id=organisation_id
    ).one()

    organisation.services.append(service)


def dao_get_invited_organisation_user(user_id):
    return InvitedOrganisationUser.query.filter_by(id=user_id).one()


def dao_get_users_for_organisation(organisation_id):
    return User.query.filter(
        User.organisations.any(id=organisation_id),
        User.state == 'active'
    ).order_by(User.created_at).all()


@transactional
def dao_add_user_to_organisation(organisation_id, user_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    user = User.query.filter_by(id=user_id).one()
    user.organisations.append(organisation)
    db.session.add(organisation)
    return user
