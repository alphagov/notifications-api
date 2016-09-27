def test_job_schema_doesnt_return_notifications(sample_notification_with_job):
    from app.schemas import job_schema

    job = sample_notification_with_job.job
    assert job.notifications.count() == 1

    data, errors = job_schema.dump(job)

    assert not errors
    assert 'notifications' not in data


def test_notification_schema_ignores_absent_api_key(sample_notification_with_job):
    from app.schemas import notification_with_template_schema

    data = notification_with_template_schema.dump(sample_notification_with_job).data
    assert data['key_name'] is None


def test_notification_schema_adds_api_key_name(sample_notification_with_api_key):
    from app.schemas import notification_with_template_schema

    data = notification_with_template_schema.dump(sample_notification_with_api_key).data
    assert data['key_name'] == 'Test key'
