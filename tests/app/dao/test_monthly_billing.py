import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.dao.monthly_billing_dao import update_monthly_billing
from app.models import MonthlyBilling


def test_add_monthly_billing_only_allows_one_row_per_service_month_type(sample_service):
    first = MonthlyBilling(id=uuid.uuid4(),
                           service_id=sample_service.id,
                           notification_type='sms',
                           month='January',
                           year='2017',
                           monthly_totals={'billing_units': 100,
                                           'rate': 0.0158})

    second = MonthlyBilling(id=uuid.uuid4(),
                            service_id=sample_service.id,
                            notification_type='sms',
                            month='January',
                            year='2017',
                            monthly_totals={'billing_units': 50,
                                            'rate': 0.0162})

    update_monthly_billing(first)
    with pytest.raises(IntegrityError):
        update_monthly_billing(second)
        monthly = MonthlyBilling.query.all()
        assert len(monthly) == 1
        assert monthly[0].monthly_totals == {'billing_units': 100,
                                             'rate': 0.0158}
