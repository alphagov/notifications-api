from app.celery.statistics_tasks import (
    record_initial_job_statistics,
    record_outcome_job_statistics,
    create_initial_notification_statistic_tasks,
    create_outcome_notification_statistic_tasks)
from sqlalchemy.exc import SQLAlchemyError
from app import create_uuid
from tests.app.conftest import sample_notification


def test_should_create_initial_job_task_if_notification_is_related_to_a_job(
        notify_db, notify_db_session, sample_job, mocker
):
    mock = mocker.patch("app.celery.statistics_tasks.record_initial_job_statistics.apply_async")
    notification = sample_notification(notify_db, notify_db_session, job=sample_job)
    create_initial_notification_statistic_tasks(notification)
    mock.assert_called_once_with((str(notification.id), ), queue="statistics")


def test_should_not_create_initial_job_task_if_notification_is_related_to_a_job(
        notify_db, notify_db_session, sample_notification, mocker
):
    mock = mocker.patch("app.celery.statistics_tasks.record_initial_job_statistics.apply_async")
    create_initial_notification_statistic_tasks(sample_notification)
    mock.assert_not_called()


def test_should_create_outcome_job_task_if_notification_is_related_to_a_job(
        notify_db, notify_db_session, sample_job, mocker
):
    mock = mocker.patch("app.celery.statistics_tasks.record_outcome_job_statistics.apply_async")
    notification = sample_notification(notify_db, notify_db_session, job=sample_job)
    create_outcome_notification_statistic_tasks(notification)
    mock.assert_called_once_with((str(notification.id), ), queue="statistics")


def test_should_not_create_outcome_job_task_if_notification_is_related_to_a_job(
        notify_db, notify_db_session, sample_notification, mocker
):
    mock = mocker.patch("app.celery.statistics_tasks.record_outcome_job_statistics.apply_async")
    create_outcome_notification_statistic_tasks(sample_notification)
    mock.assert_not_called()


def test_should_call_create_job_stats_dao_methods(notify_db, notify_db_session, sample_notification, mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.create_or_update_job_sending_statistics")
    record_initial_job_statistics(str(sample_notification.id))

    dao_mock.assert_called_once_with(sample_notification)


def test_should_retry_if_persisting_the_job_stats_has_a_sql_alchemy_exception(
        notify_db,
        notify_db_session,
        sample_notification,
        mocker):
    dao_mock = mocker.patch(
        "app.celery.statistics_tasks.create_or_update_job_sending_statistics",
        side_effect=SQLAlchemyError()
    )
    retry_mock = mocker.patch('app.celery.statistics_tasks.record_initial_job_statistics.retry')

    record_initial_job_statistics(str(sample_notification.id))
    dao_mock.assert_called_once_with(sample_notification)
    retry_mock.assert_called_with(queue="retry")


def test_should_call_update_job_stats_dao_outcome_methods(notify_db, notify_db_session, sample_notification, mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.update_job_stats_outcome_count")
    record_outcome_job_statistics(str(sample_notification.id))

    dao_mock.assert_called_once_with(sample_notification)


def test_should_retry_if_persisting_the_job_outcome_stats_has_a_sql_alchemy_exception(
        notify_db,
        notify_db_session,
        sample_notification,
        mocker):
    dao_mock = mocker.patch(
        "app.celery.statistics_tasks.update_job_stats_outcome_count",
        side_effect=SQLAlchemyError()
    )
    retry_mock = mocker.patch('app.celery.statistics_tasks.record_outcome_job_statistics.retry')

    record_outcome_job_statistics(str(sample_notification.id))
    dao_mock.assert_called_once_with(sample_notification)
    retry_mock.assert_called_with(queue="retry")


def test_should_retry_if_persisting_the_job_outcome_stats_updates_zero_rows(
        notify_db,
        notify_db_session,
        sample_notification,
        mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.update_job_stats_outcome_count", return_value=0)
    retry_mock = mocker.patch('app.celery.statistics_tasks.record_outcome_job_statistics.retry')

    record_outcome_job_statistics(str(sample_notification.id))
    dao_mock.assert_called_once_with(sample_notification)
    retry_mock.assert_called_with(queue="retry")


def test_should_retry_if_persisting_the_job_stats_creation_cant_find_notification_by_id(
        notify_db,
        notify_db_session,
        mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.create_or_update_job_sending_statistics")
    retry_mock = mocker.patch('app.celery.statistics_tasks.record_initial_job_statistics.retry')

    record_initial_job_statistics(str(create_uuid()))
    dao_mock.assert_not_called()
    retry_mock.assert_called_with(queue="retry")


def test_should_retry_if_persisting_the_job_stats_outcome_cant_find_notification_by_id(
        notify_db,
        notify_db_session,
        mocker):

    dao_mock = mocker.patch("app.celery.statistics_tasks.update_job_stats_outcome_count")
    retry_mock = mocker.patch('app.celery.statistics_tasks.record_outcome_job_statistics.retry')

    record_outcome_job_statistics(str(create_uuid()))
    dao_mock.assert_not_called()
    retry_mock.assert_called_with(queue="retry")
