from datetime import datetime
import uuid

from app.dao.jobs_dao import (
    dao_get_job_by_service_id_and_job_id,
    dao_create_job,
    dao_update_job,
    dao_get_jobs_by_service_id
)

from app.models import Job


def test_create_job(sample_template):
    assert Job.query.count() == 0

    job_id = uuid.uuid4()
    data = {
        'id': job_id,
        'service_id': sample_template.service.id,
        'template_id': sample_template.id,
        'original_file_name': 'some.csv',
        'notification_count': 1
    }

    job = Job(**data)
    dao_create_job(job)

    assert Job.query.count() == 1
    job_from_db = Job.query.get(job_id)
    assert job == job_from_db


def test_get_job_by_id(sample_job):
    job_from_db = dao_get_job_by_service_id_and_job_id(sample_job.service.id, sample_job.id)
    assert sample_job == job_from_db


def test_get_jobs_for_service(notify_db, notify_db_session, sample_template):
    from tests.app.conftest import sample_job as create_job
    from tests.app.conftest import sample_service as create_service
    from tests.app.conftest import sample_template as create_template
    from tests.app.conftest import sample_user as create_user

    one_job = create_job(notify_db, notify_db_session, sample_template.service, sample_template)

    other_user = create_user(notify_db, notify_db_session, email="test@digital.cabinet-office.gov.uk")
    other_service = create_service(notify_db, notify_db_session, user=other_user, service_name="other service",
                                   email_from='other.service')
    other_template = create_template(notify_db, notify_db_session, service=other_service)
    other_job = create_job(notify_db, notify_db_session, service=other_service, template=other_template)

    one_job_from_db = dao_get_jobs_by_service_id(one_job.service_id)
    other_job_from_db = dao_get_jobs_by_service_id(other_job.service_id)

    assert len(one_job_from_db) == 1
    assert one_job == one_job_from_db[0]

    assert len(other_job_from_db) == 1
    assert other_job == other_job_from_db[0]

    assert one_job_from_db != other_job_from_db


def test_get_jobs_for_service_in_created_at_order(notify_db, notify_db_session, sample_template):
    from tests.app.conftest import sample_job as create_job

    job_1 = create_job(
        notify_db, notify_db_session, sample_template.service, sample_template, created_at=datetime.utcnow())
    job_2 = create_job(
        notify_db, notify_db_session, sample_template.service, sample_template, created_at=datetime.utcnow())
    job_3 = create_job(
        notify_db, notify_db_session, sample_template.service, sample_template, created_at=datetime.utcnow())
    job_4 = create_job(
        notify_db, notify_db_session, sample_template.service, sample_template, created_at=datetime.utcnow())

    jobs = dao_get_jobs_by_service_id(sample_template.service.id)

    assert len(jobs) == 4
    assert jobs[0].id == job_4.id
    assert jobs[1].id == job_3.id
    assert jobs[2].id == job_2.id
    assert jobs[3].id == job_1.id


def test_update_job(sample_job):
    assert sample_job.status == 'pending'

    sample_job.status = 'in progress'

    dao_update_job(sample_job)

    job_from_db = Job.query.get(sample_job.id)

    assert job_from_db.status == 'in progress'
