from datetime import date, datetime

from freezegun import freeze_time

from app.models import SMS_TYPE, EMAIL_TYPE
from tests.app.db import create_service, create_template, create_ft_notification_status, create_notification


@freeze_time('2018-06-01')
def test_get_platform_stats_uses_todays_date_if_no_start_or_end_date_is_provided(admin_request, mocker):
    today = datetime.now().date()
    dao_mock = mocker.patch('app.platform_stats.rest.fetch_notification_status_totals_for_all_services')
    mocker.patch('app.service.rest.statistics.format_statistics')

    admin_request.get('platform_stats.get_platform_stats')

    dao_mock.assert_called_once_with(start_date=today, end_date=today)


def test_get_platform_stats_can_filter_by_date(admin_request, mocker):
    start_date = date(2017, 1, 1)
    end_date = date(2018, 1, 1)
    dao_mock = mocker.patch('app.platform_stats.rest.fetch_notification_status_totals_for_all_services')
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


@freeze_time('2018-10-31 14:00')
def test_get_platform_stats_with_real_query(admin_request, notify_db_session):
    service_1 = create_service(service_name='service_1')
    sms_template = create_template(service=service_1, template_type=SMS_TYPE)
    email_template = create_template(service=service_1, template_type=EMAIL_TYPE)
    create_ft_notification_status(date(2018, 10, 29), 'sms', service_1, count=10)
    create_ft_notification_status(date(2018, 10, 29), 'email', service_1, count=3)

    create_notification(sms_template, created_at=datetime(2018, 10, 31, 11, 0, 0), key_type='test')
    create_notification(sms_template, created_at=datetime(2018, 10, 31, 12, 0, 0), status='delivered')
    create_notification(email_template, created_at=datetime(2018, 10, 31, 13, 0, 0), status='delivered')

    response = admin_request.get(
        'platform_stats.get_platform_stats', start_date=date(2018, 10, 29),
    )
    assert response == {
        'email': {
            'failures': {
                'virus-scan-failed': 0, 'temporary-failure': 0, 'permanent-failure': 0, 'technical-failure': 0},
            'total': 4, 'test-key': 0
        },
        'letter': {
            'failures': {
                'virus-scan-failed': 0, 'temporary-failure': 0, 'permanent-failure': 0, 'technical-failure': 0},
            'total': 0, 'test-key': 0
        },
        'sms': {
            'failures': {
                'virus-scan-failed': 0, 'temporary-failure': 0, 'permanent-failure': 0, 'technical-failure': 0},
            'total': 11, 'test-key': 1
        }
    }
