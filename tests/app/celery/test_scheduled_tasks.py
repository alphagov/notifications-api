from datetime import datetime, timedelta

from flask import current_app

from app.celery import scheduled_tasks
from app.celery.scheduled_tasks import (delete_verify_codes,
                                        delete_successful_notifications,
                                        delete_failed_notifications,
                                        delete_invitations,
                                        timeout_notifications)
from tests.app.conftest import sample_notification


def test_should_call_delete_notifications_more_than_week_in_task(notify_api, mocker):
    mocked = mocker.patch('app.celery.scheduled_tasksgit .delete_notifications_created_more_than_a_week_ago')
    delete_successful_notifications()
    assert mocked.assert_called_with('delivered')
    assert scheduled_tasks.delete_notifications_created_more_than_a_week_ago.call_count == 1


def test_should_call_delete_notifications_more_than_week_in_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_notifications_created_more_than_a_week_ago')
    delete_failed_notifications()
    assert scheduled_tasks.delete_notifications_created_more_than_a_week_ago.call_count == 4


def test_should_call_delete_codes_on_delete_verify_codes_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_codes_older_created_more_than_a_day_ago')
    delete_verify_codes()
    assert scheduled_tasks.delete_codes_older_created_more_than_a_day_ago.call_count == 1


def test_should_call_delete_invotations_on_delete_invitations_task(notify_api, mocker):
    mocker.patch('app.celery.scheduled_tasks.delete_invitations_created_more_than_two_days_ago')
    delete_invitations()
    assert scheduled_tasks.delete_invitations_created_more_than_two_days_ago.call_count == 1


def test_update_status_of_notifications_after_timeout(notify_api,
                                                      notify_db,
                                                      notify_db_session,
                                                      sample_service,
                                                      sample_template,
                                                      mmg_provider):
    with notify_api.test_request_context():
        not1 = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') + 10))
        timeout_notifications()
        assert not1.status == 'temporary-failure'


def test_not_update_status_of_notification_before_timeout(notify_api,
                                                          notify_db,
                                                          notify_db_session,
                                                          sample_service,
                                                          sample_template,
                                                          mmg_provider):
    with notify_api.test_request_context():
        not1 = sample_notification(
            notify_db,
            notify_db_session,
            service=sample_service,
            template=sample_template,
            status='sending',
            created_at=datetime.utcnow() - timedelta(
                seconds=current_app.config.get('SENDING_NOTIFICATIONS_TIMEOUT_PERIOD') - 10))
        timeout_notifications()
        assert not1.status == 'sending'
