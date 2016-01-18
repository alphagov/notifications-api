import uuid

from app.dao.jobs_dao import (
    save_job,
    get_job_by_id,
    get_jobs_by_service,
    get_jobs
)

from app.models import Job


def test_save_job(notify_db, notify_db_session, sample_template):

    assert Job.query.count() == 0

    job_id = uuid.uuid4()
    bucket_name = 'service-{}-notify'.format(sample_template.service.id)
    file_name = '{}.csv'.format(job_id)
    data = {
        'id': job_id,
        'service_id': sample_template.service.id,
        'template_id': sample_template.id,
        'bucket_name': bucket_name,
        'file_name': file_name,
        'original_file_name': 'some.csv'
    }

    job = Job(**data)
    save_job(job)

    assert Job.query.count() == 1
    job_from_db = Job.query.get(job_id)
    assert job == job_from_db


def test_get_job_by_id(notify_db, notify_db_session, sample_job):
    job_from_db = get_job_by_id(sample_job.id)
    assert sample_job == job_from_db


def test_get_jobs_for_service(notify_db, notify_db_session, sample_job):

    service_id = sample_job.service_id
    job_from_db = get_jobs_by_service(service_id)

    assert len(job_from_db) == 1
    assert sample_job == job_from_db[0]


def test_get_all_jobs(notify_db, notify_db_session, sample_template):
    from tests.app.conftest import sample_job as create_job
    for i in range(5):
        create_job(notify_db,
                   notify_db_session,
                   sample_template.service,
                   sample_template)
    jobs_from_db = get_jobs()
    assert len(jobs_from_db) == 5
