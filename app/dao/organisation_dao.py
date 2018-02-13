from app import db
from app.dao.dao_utils import transactional
from app.models import Organisation


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
