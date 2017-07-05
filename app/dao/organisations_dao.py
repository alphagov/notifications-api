from app import db
from app.dao.dao_utils import transactional, version_class
from app.models import Organisation


def dao_get_organisations():
    return Organisation.query.all()


def dao_get_organisation_by_id(org_id):
    return Organisation.query.filter_by(id=org_id).one()


@transactional
@version_class(Organisation)
def dao_create_organisation(organisation):
    db.session.add(organisation)


@transactional
@version_class(Organisation)
def dao_update_organisation(organisation):
    db.session.add(organisation)
