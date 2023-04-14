from app import db
from app.dao.dao_utils import autocommit
from app.models import OrganisationPermission


@autocommit
def set_organisation_permission(organisation, permissions):
    query = OrganisationPermission.query.filter_by(organisation=organisation)
    query.delete()
    for p in permissions:
        o_p = OrganisationPermission(organisation_id=organisation.id, permission=p)
        o_p.organisation = organisation
        db.session.add(o_p)
