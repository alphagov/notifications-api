from datetime import datetime
from decimal import Decimal
from app.dao.provider_rates_dao import create_provider_rates
from app.models import ProviderRates


def test_create_provider_rates(notify_db, notify_db_session, mmg_provider_name):
    now = datetime.utcnow()
    rate = Decimal("1.00000")
    create_provider_rates(mmg_provider_name, now, rate)
    assert ProviderRates.query.count() == 1
    assert ProviderRates.query.first().rate == rate
    assert ProviderRates.query.first().valid_from == now
    assert ProviderRates.query.first().provider == mmg_provider_name
