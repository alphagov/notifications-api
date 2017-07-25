from app.models import ProviderRates, ProviderDetails
from app import db
from app.dao.dao_utils import transactional


@transactional
def create_provider_rates(provider_identifier, valid_from, rate):
    provider = ProviderDetails.query.filter_by(identifier=provider_identifier).one()

    provider_rates = ProviderRates(provider_id=provider.id, valid_from=valid_from, rate=rate)
    db.session.add(provider_rates)
