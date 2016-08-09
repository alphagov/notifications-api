from app.models import Organisation


def dao_get_organisations():
    return Organisation.query.all()


def dao_get_organisation_by_id(org_id):
    return Organisation.query.filter_by(id=org_id).one()
