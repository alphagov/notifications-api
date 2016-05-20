from datetime import date, timedelta

from flask import json
from freezegun import freeze_time

from tests import create_authorization_header
from tests.app.conftest import (
    sample_notification_statistics as create_sample_notification_statistics,
    sample_service as create_sample_service
)


def test_get_notification_statistics(notify_api, sample_notification_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_notification_statistics.service_id
            )

            response = client.get(
                '/notifications/statistics?day={}'.format(date.today().isoformat()),
                headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))

            assert len(notifications['data']) == 1
            stats = notifications['data'][0]
            assert stats['emails_requested'] == 2
            assert stats['emails_delivered'] == 1
            assert stats['emails_failed'] == 1
            assert stats['sms_requested'] == 2
            assert stats['sms_delivered'] == 1
            assert stats['sms_failed'] == 1
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
                '/notifications/statistics?day={}'.format(date.today().isoformat()),
                headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))

            assert len(notifications['data']) == 1
            assert notifications['data'][0]['day'] == date.today().isoformat()
            assert response.status_code == 200


def test_get_notification_statistics_fails_if_no_date(notify_api, sample_notification_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_notification_statistics.service_id
            )

            response = client.get(
                '/notifications/statistics',
                headers=[auth_header]
            )

            resp = json.loads(response.get_data(as_text=True))
            assert resp['result'] == 'error'
            assert resp['message'] == {'day': ['Missing data for required field.']}
            assert response.status_code == 400


def test_get_notification_statistics_fails_if_invalid_date(notify_api, sample_notification_statistics):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_notification_statistics.service_id
            )

            response = client.get(
                '/notifications/statistics?day=2016-99-99',
                headers=[auth_header]
            )

            resp = json.loads(response.get_data(as_text=True))
            assert resp['result'] == 'error'
            assert resp['message'] == {'day': ['Not a valid date.']}
            assert response.status_code == 400


def test_get_notification_statistics_returns_zeros_if_not_in_db(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_service.id
            )

            response = client.get(
                '/notifications/statistics?day={}'.format(date.today().isoformat()),
                headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))

            assert len(notifications['data']) == 1
            stats = notifications['data'][0]
            assert stats['emails_requested'] == 0
            assert stats['emails_delivered'] == 0
            assert stats['emails_failed'] == 0
            assert stats['sms_requested'] == 0
            assert stats['sms_delivered'] == 0
            assert stats['sms_failed'] == 0
            assert stats['service'] == str(sample_service.id)
            assert response.status_code == 200


def test_get_notification_statistics_returns_both_existing_stats_and_generated_zeros(
    notify_api,
    notify_db,
    notify_db_session
):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_with_stats = create_sample_service(
                notify_db,
                notify_db_session,
                service_name='service_with_stats',
                email_from='service_with_stats'
            )
            service_without_stats = create_sample_service(
                notify_db,
                notify_db_session,
                service_name='service_without_stats',
                email_from='service_without_stats'
            )
            notification_statistics = create_sample_notification_statistics(
                notify_db,
                notify_db_session,
                service=service_with_stats,
                day=date.today()
            )
            auth_header = create_authorization_header(
                service_id=service_with_stats.id
            )

            response = client.get(
                '/notifications/statistics?day={}'.format(date.today().isoformat()),
                headers=[auth_header]
            )

            notifications = json.loads(response.get_data(as_text=True))

            assert len(notifications['data']) == 2
            retrieved_stats = notifications['data'][0]
            generated_stats = notifications['data'][1]

            assert retrieved_stats['emails_requested'] == 2
            assert retrieved_stats['emails_delivered'] == 1
            assert retrieved_stats['emails_failed'] == 1
            assert retrieved_stats['sms_requested'] == 2
            assert retrieved_stats['sms_delivered'] == 1
            assert retrieved_stats['sms_failed'] == 1
            assert retrieved_stats['service'] == str(service_with_stats.id)

            assert generated_stats['emails_requested'] == 0
            assert generated_stats['emails_delivered'] == 0
            assert generated_stats['emails_failed'] == 0
            assert generated_stats['sms_requested'] == 0
            assert generated_stats['sms_delivered'] == 0
            assert generated_stats['sms_failed'] == 0
            assert generated_stats['service'] == str(service_without_stats.id)

            assert response.status_code == 200
