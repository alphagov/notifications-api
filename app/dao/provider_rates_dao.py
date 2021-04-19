from app import db
from app.dao.dao_utils import autocommit
from app.models import ProviderDetails, ProviderRates


@autocommit
def create_provider_rates(provider_identifier, valid_from, rate):
    provider = ProviderDetails.query.filter_by(identifier=provider_identifier).one()

    provider_rates = ProviderRates(provider_id=provider.id, valid_from=valid_from, rate=rate)
    db.session.add(provider_rates)
