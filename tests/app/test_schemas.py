import pytest

from marshmallow import ValidationError
from sqlalchemy import desc

from app.dao.provider_details_dao import dao_update_provider_details
from app.models import ProviderDetailsHistory


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
def test_user_update_schema_accepts_valid_attribute_pairs(user_attribute, user_value):
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
def test_user_update_schema_rejects_invalid_attribute_pairs(user_attribute, user_value):
    from app.schemas import user_update_schema_load_json
    update_dict = {
        user_attribute: user_value
    }

    with pytest.raises(ValidationError):
        data, errors = user_update_schema_load_json.load(update_dict)


@pytest.mark.parametrize('user_attribute', [
    'id', 'updated_at', 'created_at', 'user_to_service',
    '_password', 'verify_codes', 'logged_in_at', 'password_changed_at',
    'failed_login_count', 'state', 'platform_admin'
])
def test_user_update_schema_rejects_disallowed_attribute_keys(user_attribute):
    update_dict = {
        user_attribute: 'not important'
    }
    from app.schemas import user_update_schema_load_json

    with pytest.raises(ValidationError) as excinfo:
        data, errors = user_update_schema_load_json.load(update_dict)

    assert excinfo.value.messages['_schema'][0] == 'Unknown field name {}'.format(user_attribute)


def test_provider_details_schema_returns_user_details(
    mocker,
    sample_user,
    current_sms_provider
):
    from app.schemas import provider_details_schema
    mocker.patch('app.provider_details.switch_providers.get_user_by_id', return_value=sample_user)
    current_sms_provider.created_by = sample_user
    data = provider_details_schema.dump(current_sms_provider).data

    assert sorted(data['created_by'].keys()) == sorted(['id', 'email_address', 'name'])


def test_provider_details_history_schema_returns_user_details(
    mocker,
    sample_user,
    restore_provider_details,
    current_sms_provider
):
    from app.schemas import provider_details_schema
    mocker.patch('app.provider_details.switch_providers.get_user_by_id', return_value=sample_user)
    current_sms_provider.created_by_id = sample_user.id
    data = provider_details_schema.dump(current_sms_provider).data

    dao_update_provider_details(current_sms_provider)

    current_sms_provider_in_history = ProviderDetailsHistory.query.filter(
        ProviderDetailsHistory.id == current_sms_provider.id
    ).order_by(
        desc(ProviderDetailsHistory.version)
    ).first()
    data = provider_details_schema.dump(current_sms_provider_in_history).data

    assert sorted(data['created_by'].keys()) == sorted(['id', 'email_address', 'name'])
