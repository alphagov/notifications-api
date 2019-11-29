from app.dao.date_util import get_current_financial_year_start_year
from freezegun import freeze_time
from tests.app.db import create_service, create_notification, create_template
from app.service.utils import get_services_with_high_failure_rates


# see get_financial_year for conversion of financial years.
@freeze_time("2017-03-31 22:59:59.999999")
def test_get_current_financial_year_start_year_before_march():
    current_fy = get_current_financial_year_start_year()
    assert current_fy == 2016


@freeze_time("2017-03-31 23:00:00.000000")
def test_get_current_financial_year_start_year_after_april():
    current_fy = get_current_financial_year_start_year()
    assert current_fy == 2017


@freeze_time("2019-12-02 12:00:00.000000")
def test_get_services_with_high_failure_rates(notify_db_session):
    service_1 = create_service(service_name="Service 1")
    service_3 = create_service(service_name="Service 3", restricted=True)  # restricted
    service_4 = create_service(service_name="Service 4", research_mode=True)  # research mode
    service_5 = create_service(service_name="Service 5", active=False)  # not active
    services = [service_1, service_3, service_4, service_5]
    for service in services:
        template = create_template(service)
        create_notification(template, status="permanent-failure")
        for x in range(0, 3):
            create_notification(template, status="delivered")

    service_6 = create_service(service_name="Service 6")  # notifications too old
    with freeze_time("2019-11-30 15:00:00.000000"):
        template_6 = create_template(service_6)
        for x in range(0, 4):
            create_notification(template_6, status="permanent-failure")

    service_2 = create_service(service_name="Service 2")  # below threshold
    template_2 = create_template(service_2)
    create_notification(template_2, status="permanent-failure")

    assert get_services_with_high_failure_rates(threshold=3) == [{
        'id': str(service_1.id),
        'name': service_1.name,
        'permanent_failure_rate': 0.25
    }]
