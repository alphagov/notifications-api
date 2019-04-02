from app import performance_platform_client
from app.dao.fact_notification_status_dao import get_total_sent_notifications_for_day_and_type
from app.utils import get_london_midnight_in_utc


def send_total_notifications_sent_for_day_stats(date, notification_type, count):
    payload = performance_platform_client.format_payload(
        dataset='notifications',
        date=date,
        group_name='channel',
        group_value=notification_type,
        count=count
    )

    performance_platform_client.send_stats_to_performance_platform(payload)


def get_total_sent_notifications_for_day(day):
    email_count = get_total_sent_notifications_for_day_and_type(day, 'email')
    sms_count = get_total_sent_notifications_for_day_and_type(day, 'sms')
    letter_count = get_total_sent_notifications_for_day_and_type(day, 'letter')

    start_date = get_london_midnight_in_utc(day)

    return {
        "start_date": start_date,
        "email": {
            "count": email_count
        },
        "sms": {
            "count": sms_count
        },
        "letter": {
            "count": letter_count
        },
    }
