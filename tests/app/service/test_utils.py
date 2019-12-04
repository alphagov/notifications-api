from app.dao.date_util import get_current_financial_year_start_year
from freezegun import freeze_time
from app.service.utils import get_services_with_high_failure_rates
from collections import namedtuple
from datetime import datetime, timedelta


# see get_financial_year for conversion of financial years.
@freeze_time("2017-03-31 22:59:59.999999")
def test_get_current_financial_year_start_year_before_march():
    current_fy = get_current_financial_year_start_year()
    assert current_fy == 2016


@freeze_time("2017-03-31 23:00:00.000000")
def test_get_current_financial_year_start_year_after_april():
    current_fy = get_current_financial_year_start_year()
    assert current_fy == 2017


MockServicesNotificationCounts = namedtuple(
    'ServicesSendingToTVNumbers',
    [
        'service_id',
        'status',
        'count',
    ]
)


@freeze_time("2019-12-02 12:00:00.000000")
def test_get_services_with_high_failure_rates(mocker, notify_db_session):
    mock_query_results = [
        MockServicesNotificationCounts('123', 'delivered', 150),
        MockServicesNotificationCounts('123', 'permanent-failure', 50),  # these will show up
        MockServicesNotificationCounts('456', 'delivered', 150),
        MockServicesNotificationCounts('456', 'permanent-failure', 5),  # ratio too low
        MockServicesNotificationCounts('789', 'permanent-failure', 5),  # below threshold
        MockServicesNotificationCounts('444', 'delivered', 100),
        MockServicesNotificationCounts('444', 'permanent-failure', 100),  # these will show up
    ]
    mocker.patch(
        'app.service.utils.dao_find_real_sms_notification_count_by_status_for_live_services',
        return_value=mock_query_results
    )
    start_date = (datetime.utcnow() - timedelta(days=1))
    end_date = datetime.utcnow()

    assert get_services_with_high_failure_rates(start_date, end_date) == [
        {'id': '123', 'permanent_failure_rate': 0.25},
        {'id': '444', 'permanent_failure_rate': 0.5}
    ]
