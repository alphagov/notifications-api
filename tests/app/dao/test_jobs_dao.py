import uuid

from app.dao.jobs_dao import (
    save_job,
    get_job_by_id,
    get_jobs_by_service,
    get_jobs
)

from app.models import Job

from tests.app.conftest import (
    sample_template as create_template,
    sample_service as create_service
)


def test_save_job(notify_api, notify_db, notify_db_session, sample_user):
    service = create_service(notify_db, notify_db_session, user=sample_user)
    template = create_template(notify_db, notify_db_session, service=service)

    assert Job.query.count() == 0
    job_id = uuid.uuid4()
    data = {
        'id': job_id,
        'service_id': service.id,
        'template_id': template.id,
        'original_file_name': 'some.csv'
    }

    job = Job(**data)

    save_job(job)

    assert Job.query.count() == 1
    job_from_db = Job.query.get(job_id)
    assert job == job_from_db


def test_get_job_by_id(notify_api, notify_db, notify_db_session, sample_user):
    service = create_service(notify_db, notify_db_session, user=sample_user)
    template = create_template(notify_db, notify_db_session, service=service)

    assert Job.query.count() == 0
    job_id = uuid.uuid4()
    data = {
        'id': job_id,
        'service_id': service.id,
        'template_id': template.id,
        'original_file_name': 'some.csv'
    }
    job = Job(**data)
    save_job(job)

    job_from_db = get_job_by_id(job_id)

    assert job == job_from_db


def test_get_jobs_for_service(notify_api, notify_db, notify_db_session,
                              sample_user):

    service1, service2 = _do_services_setup(notify_db,
                                            notify_db_session,  sample_user)

    jobs1 = [job for job in service1.jobs]  # get jobs directly from service
    jobs1_from_dao = get_jobs_by_service(service1.id)  # get jobs via dao

    assert len(jobs1_from_dao) == 5
    assert jobs1 == jobs1_from_dao

    jobs2 = [job for job in service2.jobs]  # get jobs directly from service
    jobs2_from_dao = get_jobs_by_service(service2.id)  # get jobs via dao

    assert len(jobs2_from_dao) == 2
    assert jobs2 == jobs2_from_dao

    assert jobs1_from_dao != jobs2_from_dao


def test_get_all_jobs(notify_api, notify_db, notify_db_session,
                      sample_user):

    _do_services_setup(notify_db, notify_db_session, sample_user)

    jobs_from_db = get_jobs()
    assert len(jobs_from_db) == 7


def _do_services_setup(notify_db, notify_db_session, sample_user):
    service1 = create_service(notify_db, notify_db_session, user=sample_user)
    template1 = create_template(notify_db, notify_db_session, service=service1)

    for i in range(5):
        job_id = uuid.uuid4()
        data = {
            'id': job_id,
            'service_id': service1.id,
            'template_id': template1.id,
            'original_file_name': 'some.csv'
        }
        save_job(Job(**data))

    service2 = create_service(notify_db, notify_db_session, user=sample_user)
    template2 = create_template(notify_db, notify_db_session, service=service2)

    for i in range(2):
        job_id = uuid.uuid4()
        data = {
            'id': job_id,
            'service_id': service2.id,
            'template_id': template2.id,
            'original_file_name': 'some.csv'
        }
        save_job(Job(**data))

    return service1, service2
