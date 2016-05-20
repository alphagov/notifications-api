from datetime import date, timedelta

from flask import json
from freezegun import freeze_time

from tests import create_authorization_header
from tests.app.conftest import sample_notification_statistics as create_sample_notification_statistics


def test_get_notification_statistics(notify_api, sample_notification_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_notification_statistics.service_id
            )

            response = client.get(
                '/notifications/statistics',
                headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))
            stats = notifications['data'][0]
            assert stats['emails_requested'] == 2
            assert stats['emails_delivered'] == 1
            assert stats['emails_failed'] == 1
            assert stats['sms_requested'] == 2
            assert stats['sms_delivered'] == 1
            assert stats['service'] == str(sample_notification_statistics.service_id)
            assert response.status_code == 200


@freeze_time('1955-11-05T12:00:00')
def test_get_notification_statistics_only_returns_today(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            yesterdays_notification_statistics = create_sample_notification_statistics(
                notify_db,
                notify_db_session,
                service=sample_service,
                day=date.today() - timedelta(days=1)
            )
            todays_notification_statistics = create_sample_notification_statistics(
                notify_db,
                notify_db_session,
                service=sample_service,
                day=date.today()
            )
            tomorrows_notification_statistics = create_sample_notification_statistics(
                notify_db,
                notify_db_session,
                service=sample_service,
                day=date.today() + timedelta(days=1)
            )

            auth_header = create_authorization_header(
                service_id=sample_service.id
            )

            response = client.get(
                '/notifications/statistics',
                headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))
            assert len(notifications['data']) == 1
            assert notifications['data'][0]['day'] == date.today().isoformat()
            assert response.status_code == 200
