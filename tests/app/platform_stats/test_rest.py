from datetime import date, datetime

from freezegun import freeze_time


@freeze_time('2018-06-01')
def test_get_platform_stats_uses_todays_date_if_no_start_or_end_date_is_provided(admin_request, mocker):
    today = datetime.now().date()
    dao_mock = mocker.patch('app.platform_stats.rest.fetch_aggregate_stats_by_date_range_for_all_services')
    mocker.patch('app.service.rest.statistics.format_statistics')

    admin_request.get('platform_stats.get_platform_stats')

    dao_mock.assert_called_once_with(start_date=today, end_date=today)


def test_get_platform_stats_can_filter_by_date(admin_request, mocker):
    start_date = date(2017, 1, 1)
    end_date = date(2018, 1, 1)
    dao_mock = mocker.patch('app.platform_stats.rest.fetch_aggregate_stats_by_date_range_for_all_services')
    mocker.patch('app.service.rest.statistics.format_statistics')

    admin_request.get('platform_stats.get_platform_stats', start_date=start_date, end_date=end_date)

    dao_mock.assert_called_once_with(start_date=start_date, end_date=end_date)


def test_get_platform_stats_validates_the_date(admin_request):
    start_date = '1234-56-78'

    response = admin_request.get(
        'platform_stats.get_platform_stats', start_date=start_date,
        _expected_status=400
    )

    assert response['errors'][0]['message'] == 'start_date time data {} does not match format %Y-%m-%d'.format(
        start_date)
