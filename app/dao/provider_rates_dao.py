from app.models import ProviderRates
from app import db
from app.dao.dao_utils import transactional


@transactional
def create_provider_rates(provider, valid_from, rate):
    provider_rates = ProviderRates(provider=provider, valid_from=valid_from, rate=rate)
    db.session.add(provider_rates)
