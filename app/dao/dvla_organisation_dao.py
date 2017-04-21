from app.models import DVLAOrganisation


def dao_get_dvla_organisations():
    return DVLAOrganisation.query.all()
