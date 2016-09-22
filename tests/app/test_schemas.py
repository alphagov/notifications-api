def test_job_schema_doesnt_return_notifications(sample_notification_with_job):
    from app.schemas import job_schema

    job = sample_notification_with_job.job
    assert job.notifications.count() == 1

    data, errors = job_schema.dump(job)

    assert not errors
    assert 'notifications' not in data
