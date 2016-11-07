import pytest


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


@pytest.mark.parametrize('user_attribute, user_value', [
    ('name', 'New User'),
    ('email_address', 'newuser@mail.com'),
    ('mobile_number', '+4407700900460')
])
def test_user_schema_accepts_valid_attributes(user_attribute, user_value):
    update_dict = {
        user_attribute: user_value
    }
    from app.schemas import user_update_schema_load_json

    data, errors = user_update_schema_load_json.load(update_dict)
    assert not errors


@pytest.mark.parametrize('user_attribute, user_value', [
    ('name', None),
    ('name', ''),
    ('email_address', 'bademail@...com'),
    ('mobile_number', '+44077009')
])
def test_user_schema_rejects_invalid_attributes(user_attribute, user_value):
    from app.schemas import user_update_schema_load_json
    update_dict = {
        user_attribute: user_value
    }

    with pytest.raises(Exception):
        data, errors = user_update_schema_load_json.load(update_dict)
