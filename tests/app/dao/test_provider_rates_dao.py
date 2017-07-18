import uuid
from datetime import datetime
from decimal import Decimal
from app.dao.provider_rates_dao import create_provider_rates, create_sms_rate
from app.models import ProviderRates, ProviderDetails, Rate


def test_create_provider_rates(notify_db, notify_db_session, mmg_provider):
    now = datetime.now()
    rate = Decimal("1.00000")

    provider = ProviderDetails.query.filter_by(identifier=mmg_provider.identifier).one()

    create_provider_rates(mmg_provider.identifier, now, rate)
    assert ProviderRates.query.count() == 1
    assert ProviderRates.query.first().rate == rate
    assert ProviderRates.query.first().valid_from == now
    assert ProviderRates.query.first().provider_id == provider.id


def test_create_sms_rate():
    rate = Rate(id=uuid.uuid4(), valid_from=datetime.now(), rate=0.014, notification_type='sms')
    create_sms_rate(rate)
    rates = Rate.query.all()
    assert len(rates) == 1
    assert rates[0] == rate
