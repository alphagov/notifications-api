from datetime import datetime
from decimal import Decimal

from app.dao.fact_billing_dao import fetch_annual_billing_by_month, fetch_annual_billing_for_year
from tests.app.db import (
    create_ft_billing,
    create_service,
    create_template
)


def test_fetch_annual_billing_by_month(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for i in range(1, 32):
        record = create_ft_billing(bst_date='2018-01-{}'.format(i),
                                   service=service,
                                   template=template,
                                   notification_type='email')

    results, month = fetch_annual_billing_by_month(service_id=record.service_id,
                                                   billing_month=datetime(2018, 1, 1),
                                                   notification_type='email')
    assert len(results) == 1
    assert results[0] == (31, Decimal('31'), service.id, 'email', Decimal('0'), Decimal('1'), False)
    assert month == datetime(2018, 1, 1)


def test_fetch_annual_billing_for_year(notify_db_session):
    service = create_service()
    template = create_template(service=service, template_type="email")
    for i in range(1, 31):
        create_ft_billing(bst_date='2018-06-{}'.format(i),
                          service=service,
                          template=template,
                          notification_type='email')
    results = fetch_annual_billing_for_year(service_id=service.id,
                                            year=2018)

    assert results
