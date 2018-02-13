import uuid

from flask import json
from flask import url_for
import pytest

from app.config import QueueNames
from app.models import EMAIL_TYPE, LETTERS_AS_PDF
from app.models import Job
from app.models import KEY_TYPE_NORMAL
from app.models import KEY_TYPE_TEAM
from app.models import KEY_TYPE_TEST
from app.models import LETTER_TYPE
from app.models import Notification
from app.models import NOTIFICATION_SENDING, NOTIFICATION_DELIVERED
from app.models import SMS_TYPE
from app.schema_validation import validate
from app.v2.errors import RateLimitError
from app.v2.notifications.notification_schemas import post_letter_response

from tests import create_authorization_header
from tests.app.db import create_service, create_template, create_letter_contact
from tests.conftest import set_config_values

test_address = {
    'address_line_1': 'test 1',
    'address_line_2': 'test 2',
    'postcode': 'test pc'
}


def letter_request(client, data, service_id, key_type=KEY_TYPE_NORMAL, _expected_status=201):
    resp = client.post(
        url_for('v2_notifications.post_notification', notification_type=LETTER_TYPE),
        data=json.dumps(data),
        headers=[
            ('Content-Type', 'application/json'),
            create_authorization_header(service_id=service_id, key_type=key_type)
        ]
    )
    json_resp = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == _expected_status, json_resp
    return json_resp


@pytest.mark.parametrize('reference, permission',
                         [(None, LETTER_TYPE),
                          ('reference_from_client', LETTER_TYPE),
                          (None, LETTERS_AS_PDF),
                          ('reference_from_client', LETTERS_AS_PDF)
                          ])
def test_post_letter_notification_returns_201(client, notify_db_session, mocker, reference, permission):
    service = create_service(service_permissions=[permission])
    template = create_template(service=service, template_type=LETTER_TYPE)
    data = {
        'template_id': str(template.id),
        'personalisation': {
            'address_line_1': 'Her Royal Highness Queen Elizabeth II',
            'address_line_2': 'Buckingham Palace',
            'address_line_3': 'London',
            'postcode': 'SW1 1AA',
            'name': 'Lizzie'
        }
    }
    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')

    if reference:
        data.update({'reference': reference})

    resp_json = letter_request(client, data, service_id=template.service_id)

    assert validate(resp_json, post_letter_response) == resp_json
    assert Job.query.count() == 0
    notification = Notification.query.one()
    notification_id = notification.id
    assert resp_json['id'] == str(notification_id)
    assert resp_json['reference'] == reference
    assert resp_json['content']['subject'] == template.subject
    assert resp_json['content']['body'] == template.content
    assert 'v2/notifications/{}'.format(notification_id) in resp_json['uri']
    assert resp_json['template']['id'] == str(template.id)
    assert resp_json['template']['version'] == template.version
    assert (
        'services/{}/templates/{}'.format(
            template.service_id,
            template.id
        ) in resp_json['template']['uri']
    )
    assert not resp_json['scheduled_for']
    assert not notification.reply_to_text


def test_post_letter_notification_for_letters_as_pdf_calls_celery_task(client, sample_letter_template, mocker):
    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'address_line_1': 'Her Royal Highness Queen Elizabeth II',
            'address_line_2': 'Buckingham Palace',
            'address_line_3': 'London',
            'postcode': 'SW1 1AA',
            'name': 'Lizzie'
        },
        'reference': 'foo'
    }
    fake_task = mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')

    letter_request(client, data, service_id=sample_letter_template.service_id)

    notification = Notification.query.one()

    fake_task.assert_called_once_with([str(notification.id)], queue=QueueNames.CREATE_LETTERS_PDF)


@pytest.mark.parametrize('env', [
    'development',
    'preview',
])
def test_post_letter_notification_for_letters_as_pdf_calls_create_fake_response_in_research_and_test_key_correct_env(
        notify_api, client, sample_letter_template, mocker, env):
    sample_letter_template.service.research_mode = True

    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'address_line_1': 'Her Royal Highness Queen Elizabeth II',
            'address_line_2': 'Buckingham Palace',
            'address_line_3': 'London',
            'postcode': 'SW1 1AA',
            'name': 'Lizzie'
        },
        'reference': 'foo'
    }

    fake_create_letter_task = mocker.patch('app.celery.letters_pdf_tasks.create_letters_pdf.apply_async')
    fake_create_dvla_response_task = mocker.patch(
        'app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async')

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': env
    }):
        letter_request(client, data, service_id=sample_letter_template.service_id, key_type=KEY_TYPE_TEST)

    notification = Notification.query.one()

    assert notification.status == NOTIFICATION_SENDING
    assert not fake_create_letter_task.called
    fake_create_dvla_response_task.assert_called_once_with((notification.reference,), queue=QueueNames.RESEARCH_MODE)


@pytest.mark.parametrize('env', [
    'staging',
    'live',
])
def test_post_letter_noti_for_letters_as_pdf_sets_status_delivered_in_research_and_test_key_incorrect_env(
        notify_api, client, sample_letter_template, mocker, env):
    sample_letter_template.service.research_mode = True

    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'address_line_1': 'Her Royal Highness Queen Elizabeth II',
            'address_line_2': 'Buckingham Palace',
            'address_line_3': 'London',
            'postcode': 'SW1 1AA',
            'name': 'Lizzie'
        },
        'reference': 'foo'
    }

    fake_create_letter_task = mocker.patch('app.celery.letters_pdf_tasks.create_letters_pdf.apply_async')
    fake_create_dvla_response_task = mocker.patch(
        'app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async')

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': env
    }):
        letter_request(client, data, service_id=sample_letter_template.service_id, key_type=KEY_TYPE_TEST)

    notification = Notification.query.one()

    assert not fake_create_letter_task.called
    assert not fake_create_dvla_response_task.called
    assert notification.status == NOTIFICATION_DELIVERED


@pytest.mark.parametrize('env', [
    'development',
    'preview',
    'staging',
    'live',
])
def test_post_letter_noti_for_letters_as_pdf_sets_status_to_delivered_using_test_key_and_not_research_all_env(
        notify_api, client, sample_letter_template, mocker, env):
    sample_letter_template.service.research_mode = False

    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {
            'address_line_1': 'Her Royal Highness Queen Elizabeth II',
            'address_line_2': 'Buckingham Palace',
            'address_line_3': 'London',
            'postcode': 'SW1 1AA',
            'name': 'Lizzie'
        },
        'reference': 'foo'
    }

    fake_create_letter_task = mocker.patch('app.celery.letters_pdf_tasks.create_letters_pdf.apply_async')
    fake_create_dvla_response_task = mocker.patch(
        'app.celery.research_mode_tasks.create_fake_letter_response_file.apply_async')

    with set_config_values(notify_api, {
        'NOTIFY_ENVIRONMENT': env
    }):
        letter_request(client, data, service_id=sample_letter_template.service_id, key_type=KEY_TYPE_TEST)

    notification = Notification.query.one()

    assert not fake_create_letter_task.called
    assert not fake_create_dvla_response_task.called
    assert notification.status == NOTIFICATION_DELIVERED


def test_post_letter_notification_returns_400_and_missing_template(
    client,
    sample_service_full_permissions
):
    data = {
        'template_id': str(uuid.uuid4()),
        'personalisation': test_address
    }

    error_json = letter_request(client, data, service_id=sample_service_full_permissions.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{'error': 'BadRequestError', 'message': 'Template not found'}]


def test_post_letter_notification_returns_400_for_empty_personalisation(
    client,
    sample_service_full_permissions,
    sample_letter_template
):
    data = {
        'template_id': str(sample_letter_template.id),
        'personalisation': {'address_line_1': '', 'address_line_2': '', 'postcode': ''}
    }

    error_json = letter_request(client, data, service_id=sample_service_full_permissions.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert all([e['error'] == 'ValidationError' for e in error_json['errors']])
    assert set([e['message'] for e in error_json['errors']]) == set([
        'personalisation address_line_1 is required',
        'personalisation address_line_2 is required',
        'personalisation postcode is required'
    ])


@pytest.mark.parametrize("permission", [LETTER_TYPE, LETTERS_AS_PDF])
def test_notification_returns_400_for_missing_template_field(
    client,
    permission,
    notify_db_session
):
    service = create_service(service_permissions=[permission])
    data = {
        'personalisation': test_address
    }

    error_json = letter_request(client, data, service_id=service.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert error_json['errors'] == [{
        'error': 'ValidationError',
        'message': 'template_id is a required property'
    }]


@pytest.mark.parametrize("permission", [LETTER_TYPE, LETTERS_AS_PDF])
def test_notification_returns_400_if_address_doesnt_have_underscores(
    client,
    permission,
    notify_db_session
):
    service = create_service(service_permissions=[permission])
    template = create_template(service=service, template_type=LETTER_TYPE)
    data = {
        'template_id': str(template.id),
        'personalisation': {
            'address line 1': 'Her Royal Highness Queen Elizabeth II',
            'address-line-2': 'Buckingham Palace',
            'postcode': 'SW1 1AA',
        }
    }

    error_json = letter_request(client, data, service_id=service.id, _expected_status=400)

    assert error_json['status_code'] == 400
    assert len(error_json['errors']) == 2
    assert {
        'error': 'ValidationError',
        'message': 'personalisation address_line_1 is a required property'
    } in error_json['errors']
    assert {
        'error': 'ValidationError',
        'message': 'personalisation address_line_2 is a required property'
    } in error_json['errors']


@pytest.mark.parametrize("permission", [LETTER_TYPE, LETTERS_AS_PDF])
def test_returns_a_429_limit_exceeded_if_rate_limit_exceeded(
        client,
        permission,
        notify_db_session,
        mocker
):
    service = create_service(service_permissions=[permission])
    template = create_template(service=service, template_type=LETTER_TYPE)
    persist_mock = mocker.patch('app.v2.notifications.post_notifications.persist_notification')
    mocker.patch(
        'app.v2.notifications.post_notifications.check_rate_limiting',
        side_effect=RateLimitError('LIMIT', 'INTERVAL', 'TYPE')
    )

    data = {
        'template_id': str(template.id),
        'personalisation': test_address
    }

    error_json = letter_request(client, data, service_id=service.id, _expected_status=429)

    assert error_json['status_code'] == 429
    assert error_json['errors'] == [{
        'error': 'RateLimitError',
        'message': 'Exceeded rate limit for key type TYPE of LIMIT requests per INTERVAL seconds'
    }]

    assert not persist_mock.called


@pytest.mark.parametrize('service_args', [
    {'service_permissions': [EMAIL_TYPE, SMS_TYPE]},
    {'restricted': True}
])
def test_post_letter_notification_returns_403_if_not_allowed_to_send_notification(
    client,
    notify_db_session,
    service_args
):
    service = create_service(**service_args)
    template = create_template(service, template_type=LETTER_TYPE)

    data = {
        'template_id': str(template.id),
        'personalisation': test_address
    }

    error_json = letter_request(client, data, service_id=service.id, _expected_status=400)
    assert error_json['status_code'] == 400
    assert error_json['errors'] == [
        {'error': 'BadRequestError', 'message': 'Cannot send letters'}
    ]


@pytest.mark.parametrize('research_mode, key_type, permission, final_status', [
    (True, KEY_TYPE_NORMAL, LETTER_TYPE, NOTIFICATION_SENDING),
    (False, KEY_TYPE_TEST, LETTER_TYPE, NOTIFICATION_SENDING),
    (True, KEY_TYPE_NORMAL, LETTERS_AS_PDF, NOTIFICATION_DELIVERED),
    (False, KEY_TYPE_TEST, LETTERS_AS_PDF, NOTIFICATION_DELIVERED)
])
def test_post_letter_notification_updates_noti_sending(
    client,
    notify_db_session,
    mocker,
    research_mode,
    key_type,
    permission,
    final_status
):
    service = create_service(research_mode=research_mode, service_permissions=[permission])
    template = create_template(service, template_type=LETTER_TYPE)

    data = {
        'template_id': str(template.id),
        'personalisation': {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }

    letter_request(client, data, service_id=service.id, key_type=key_type)

    notification = Notification.query.one()
    assert notification.status == final_status


@pytest.mark.parametrize("permission", [LETTER_TYPE, LETTERS_AS_PDF])
def test_post_letter_notification_doesnt_accept_team_key(client, permission, notify_db_session):
    service = create_service(service_permissions=[permission])
    template = create_template(service, template_type=LETTER_TYPE)
    data = {
        'template_id': str(template.id),
        'personalisation': {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }

    error_json = letter_request(
        client,
        data,
        service.id,
        key_type=KEY_TYPE_TEAM,
        _expected_status=403
    )

    assert error_json['status_code'] == 403
    assert error_json['errors'] == [{'error': 'BadRequestError', 'message': 'Cannot send letters with a team api key'}]


@pytest.mark.parametrize("permission", [LETTER_TYPE, LETTERS_AS_PDF])
def test_post_letter_notification_doesnt_send_in_trial(client, permission, mocker, notify_db_session):
    service = create_service(service_permissions=[permission], restricted=True)
    template = create_template(service, template_type=LETTER_TYPE)
    data = {
        'template_id': str(template.id),
        'personalisation': {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }

    error_json = letter_request(
        client,
        data,
        service.id,
        _expected_status=403
    )

    assert error_json['status_code'] == 403
    assert error_json['errors'] == [
        {'error': 'BadRequestError', 'message': 'Cannot send letters when service is in trial mode'}]


@pytest.mark.parametrize("permission, final_status",
                         [(LETTER_TYPE, NOTIFICATION_SENDING),
                          (LETTERS_AS_PDF, NOTIFICATION_DELIVERED)])
def test_post_letter_notification_fakes_dvla_when_service_is_in_trial_mode_but_using_test_key(
    client,
    permission,
    final_status,
    mocker,
    notify_db_session
):
    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')
    service = create_service(service_permissions=[permission])
    template = create_template(service, template_type=LETTER_TYPE)
    data = {
        "template_id": template.id,
        "personalisation": {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }

    letter_request(client, data=data, service_id=service.id, key_type=KEY_TYPE_TEST)

    notification = Notification.query.one()
    assert notification.status == final_status


@pytest.mark.parametrize("permission", [LETTER_TYPE, LETTERS_AS_PDF])
def test_post_letter_notification_persists_notification_reply_to_text(
    client, permission, notify_db_session, mocker
):
    mocker.patch('app.celery.tasks.letters_pdf_tasks.create_letters_pdf.apply_async')
    service = create_service(service_permissions=[permission], restricted=False)
    service_address = "12 Main Street, London"
    letter_contact = create_letter_contact(service=service, contact_block=service_address, is_default=True)
    template = create_template(service=service, template_type='letter', reply_to=letter_contact.id)
    data = {
        "template_id": template.id,
        "personalisation": {'address_line_1': 'Foo', 'address_line_2': 'Bar', 'postcode': 'Baz'}
    }
    letter_request(client, data=data, service_id=service.id, key_type=KEY_TYPE_NORMAL)

    notifications = Notification.query.all()
    assert len(notifications) == 1
    assert notifications[0].reply_to_text == service_address
