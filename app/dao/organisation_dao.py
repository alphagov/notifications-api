from app import db
from app.dao.dao_utils import transactional
from app.models import Organisation


def dao_get_organisations():
    return Organisation.query.order_by(
        Organisation.active.desc(), Organisation.name.asc()
    ).all()


def dao_get_organisation_by_id(organisation_id):
    return Organisation.query.filter_by(id=organisation_id).one()


@transactional
def dao_create_organisation(organisation):
    db.session.add(organisation)


@transactional
def dao_update_organisation(organisation_id, **kwargs):
    return Organisation.query.filter_by(id=organisation_id).update(
        kwargs
    )
