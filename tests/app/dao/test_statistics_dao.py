from app.dao.statistics_dao import persist_initial_job_statistics
from app.models import JobStatistics
from tests.app.conftest import sample_notification


def test_should_create_a_stats_entry_for_a_job(
        notify_db, notify_db_session, sample_service, sample_template, sample_job
):
    assert not len(JobStatistics.query.all())

    notification = sample_notification(
        notify_db, notify_db_session, service=sample_service, template=sample_template, job=sample_job
    )

    persist_initial_job_statistics(notification)

    stats = JobStatistics.query.all()

    assert len(stats) == 1
