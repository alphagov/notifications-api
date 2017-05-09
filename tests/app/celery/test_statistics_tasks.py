from app.celery.statistics_tasks import record_initial_job_statistics, record_outcome_job_statistics
from sqlalchemy.exc import SQLAlchemyError

import app


def test_should_call_create_job_stats_dao_methods(notify_db, notify_db_session, sample_notification, mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.create_or_update_job_sending_statistics")
    record_initial_job_statistics(sample_notification)

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

    record_initial_job_statistics(sample_notification)
    dao_mock.assert_called_once_with(sample_notification)
    retry_mock.assert_called_with(queue="retry")


def test_should_call_update_job_stats_dao_outcome_methods(notify_db, notify_db_session, sample_notification, mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.update_job_stats_outcome_count")
    record_outcome_job_statistics(sample_notification)

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

    record_outcome_job_statistics(sample_notification)
    dao_mock.assert_called_once_with(sample_notification)
    retry_mock.assert_called_with(queue="retry")


def test_should_retry_if_persisting_the_job_outcome_stats_updates_zero_rows(
        notify_db,
        notify_db_session,
        sample_notification,
        mocker):
    dao_mock = mocker.patch("app.celery.statistics_tasks.update_job_stats_outcome_count", return_value=0)
    retry_mock = mocker.patch('app.celery.statistics_tasks.record_outcome_job_statistics.retry')

    record_outcome_job_statistics(sample_notification)
    dao_mock.assert_called_once_with(sample_notification)
    retry_mock.assert_called_with(queue="retry")
