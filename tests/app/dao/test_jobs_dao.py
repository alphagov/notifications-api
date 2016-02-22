import uuid
import json

from app.dao.jobs_dao import (
    save_job,
    get_job,
    get_jobs_by_service,
    _get_jobs
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
        'original_file_name': 'some.csv',
        'notification_count': 1
    }

    job = Job(**data)
    save_job(job)

    assert Job.query.count() == 1
    job_from_db = Job.query.get(job_id)
    assert job == job_from_db


def test_get_job_by_id(notify_db, notify_db_session, sample_job):
    job_from_db = get_job(sample_job.service.id, sample_job.id)
    assert sample_job == job_from_db


def test_get_jobs_for_service(notify_db, notify_db_session, sample_template):

    from tests.app.conftest import sample_job as create_job
    from tests.app.conftest import sample_service as create_service
    from tests.app.conftest import sample_template as create_template
    from tests.app.conftest import sample_user as create_user

    one_job = create_job(notify_db, notify_db_session, sample_template.service,
                         sample_template)

    other_user = create_user(notify_db, notify_db_session,
                             email="test@digital.cabinet-office.gov.uk")
    other_service = create_service(notify_db, notify_db_session,
                                   user=other_user, service_name="other service")
    other_template = create_template(notify_db, notify_db_session,
                                     service=other_service)
    other_job = create_job(notify_db, notify_db_session, service=other_service,
                           template=other_template)

    one_job_from_db = get_jobs_by_service(one_job.service_id)
    other_job_from_db = get_jobs_by_service(other_job.service_id)

    assert len(one_job_from_db) == 1
    assert one_job == one_job_from_db[0]

    assert len(other_job_from_db) == 1
    assert other_job == other_job_from_db[0]

    assert one_job_from_db != other_job_from_db


def test_get_all_jobs(notify_db, notify_db_session, sample_template):
    from tests.app.conftest import sample_job as create_job
    for i in range(5):
        create_job(notify_db,
                   notify_db_session,
                   sample_template.service,
                   sample_template)
    jobs_from_db = _get_jobs()
    assert len(jobs_from_db) == 5


def test_update_job(notify_db, notify_db_session, sample_job):
    assert sample_job.status == 'pending'

    update_dict = {
        'id': sample_job.id,
        'service': sample_job.service.id,
        'template': sample_job.template.id,
        'bucket_name': sample_job.bucket_name,
        'file_name': sample_job.file_name,
        'original_file_name': sample_job.original_file_name,
        'status': 'in progress'
    }

    save_job(sample_job, update_dict=update_dict)

    job_from_db = Job.query.get(sample_job.id)

    assert job_from_db.status == 'in progress'
