import pytest

from app.commands import (
    insert_inbound_numbers_from_file,
    local_dev_broadcast_permissions,
    populate_annual_billing_with_defaults,
)
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers
from app.dao.services_dao import dao_add_user_to_service
from app.models import AnnualBilling
from tests.app.db import create_annual_billing, create_service, create_user


def test_insert_inbound_numbers_from_file(notify_db_session, notify_api, tmpdir):
    numbers_file = tmpdir.join("numbers.txt")
    numbers_file.write("07700900373\n07700900473\n07700900375\n\n\n\n")

    notify_api.test_cli_runner().invoke(insert_inbound_numbers_from_file, ['-f', numbers_file])

    inbound_numbers = dao_get_available_inbound_numbers()
    assert len(inbound_numbers) == 3
    assert set(x.number for x in inbound_numbers) == {'07700900373', '07700900473', '07700900375'}


def test_local_dev_broadcast_permissions(
    sample_service,
    sample_broadcast_service,
    notify_api,
):
    user = create_user()
    dao_add_user_to_service(sample_service, user)
    dao_add_user_to_service(sample_broadcast_service, user)

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) == 0

    notify_api.test_cli_runner().invoke(
        local_dev_broadcast_permissions, ['-u', user.id]
    )

    assert len(user.get_permissions(sample_service.id)) == 0
    assert len(user.get_permissions(sample_broadcast_service.id)) > 0


@pytest.mark.parametrize("organisation_type, expected_allowance",
                         [('central', 40000),
                          ('local', 20000),
                          ('nhs_gp', 10000)])
def test_populate_annual_billing_with_defaults(
        notify_db_session, notify_api, organisation_type, expected_allowance
):
    service = create_service(service_name=organisation_type, organisation_type=organisation_type)

    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ['-y', 2022]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == expected_allowance


def test_populate_annual_billing_with_defaults_sets_free_allowance_to_zero_if_previous_year_is_zero(
        notify_db_session, notify_api
):
    service = create_service(organisation_type='central')
    create_annual_billing(service_id=service.id, free_sms_fragment_limit=0, financial_year_start=2021)
    notify_api.test_cli_runner().invoke(
        populate_annual_billing_with_defaults, ['-y', 2022]
    )

    results = AnnualBilling.query.filter(
        AnnualBilling.financial_year_start == 2022,
        AnnualBilling.service_id == service.id
    ).all()

    assert len(results) == 1
    assert results[0].free_sms_fragment_limit == 0
