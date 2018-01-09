import json
import uuid
from datetime import datetime, timedelta, date
from functools import partial
from unittest.mock import ANY

import pytest
from flask import url_for, current_app
from freezegun import freeze_time

from app.celery.scheduled_tasks import daily_stats_template_usage_by_month
from app.dao.services_dao import dao_remove_user_from_service
from app.dao.templates_dao import dao_redact_template
from app.dao.users_dao import save_model_user
from app.models import (
    User, Organisation, Service, ServicePermission, Notification,
    ServiceEmailReplyTo, ServiceLetterContact,
    ServiceSmsSender, InboundNumber,
    DVLA_ORG_LAND_REGISTRY,
    KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST,
    EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, INBOUND_SMS_TYPE
)
from tests import create_authorization_header
from tests.app.conftest import (
    sample_user_service_permission as create_user_service_permission,
    sample_notification as create_sample_notification,
    sample_notification_history as create_notification_history,
    sample_notification_with_job
)
from tests.app.db import (
    create_service,
    create_template,
    create_notification,
    create_reply_to_email,
    create_letter_contact,
    create_inbound_number,
    create_service_sms_sender,
    create_service_with_defined_sms_sender
)
from tests.app.db import create_user


def test_get_service_list(client, service_factory):
    service_factory.get('one')
    service_factory.get('two')
    service_factory.get('three')
    auth_header = create_authorization_header()
    response = client.get(
        '/service',
        headers=[auth_header]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 3
    assert json_resp['data'][0]['name'] == 'one'
    assert json_resp['data'][1]['name'] == 'two'
    assert json_resp['data'][2]['name'] == 'three'


def test_get_service_list_with_only_active_flag(client, service_factory):
    inactive = service_factory.get('one')
    active = service_factory.get('two')

    inactive.active = False

    auth_header = create_authorization_header()
    response = client.get(
        '/service?only_active=True',
        headers=[auth_header]
    )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 1
    assert json_resp['data'][0]['id'] == str(active.id)


def test_get_service_list_with_user_id_and_only_active_flag(
        admin_request,
        sample_user,
        service_factory
):
    other_user = create_user(email='foo@bar.gov.uk')

    inactive = service_factory.get('one', user=sample_user)
    active = service_factory.get('two', user=sample_user)
    # from other user
    service_factory.get('three', user=other_user)

    inactive.active = False

    json_resp = admin_request.get(
        'service.get_services',
        user_id=sample_user.id,
        only_active=True
    )
    assert len(json_resp['data']) == 1
    assert json_resp['data'][0]['id'] == str(active.id)


def test_get_service_list_by_user(admin_request, sample_user, service_factory):
    other_user = create_user(email='foo@bar.gov.uk')
    service_factory.get('one', sample_user)
    service_factory.get('two', sample_user)
    service_factory.get('three', other_user)

    json_resp = admin_request.get('service.get_services', user_id=sample_user.id)
    assert len(json_resp['data']) == 2
    assert json_resp['data'][0]['name'] == 'one'
    assert json_resp['data'][1]['name'] == 'two'


def test_get_service_list_by_user_should_return_empty_list_if_no_services(admin_request, sample_service):
    # service is already created by sample user
    new_user = create_user(email='foo@bar.gov.uk')

    json_resp = admin_request.get('service.get_services', user_id=new_user.id)
    assert json_resp['data'] == []


def test_get_service_list_should_return_empty_list_if_no_services(admin_request):
    json_resp = admin_request.get('service.get_services')
    assert len(json_resp['data']) == 0


def test_get_service_by_id(admin_request, sample_service):
    json_resp = admin_request.get('service.get_service_by_id', service_id=sample_service.id)
    assert json_resp['data']['name'] == sample_service.name
    assert json_resp['data']['id'] == str(sample_service.id)
    assert not json_resp['data']['research_mode']
    assert json_resp['data']['organisation'] is None
    assert json_resp['data']['branding'] == 'govuk'
    assert json_resp['data']['dvla_organisation'] == '001'
    assert json_resp['data']['sms_sender'] == current_app.config['FROM_NUMBER']
    assert json_resp['data']['prefix_sms'] is True


@pytest.mark.parametrize('detailed', [True, False])
def test_get_service_by_id_returns_organisation_type(admin_request, sample_service, detailed):
    json_resp = admin_request.get('service.get_service_by_id', service_id=sample_service.id, detailed=detailed)
    assert json_resp['data']['organisation_type'] is None


def test_get_service_list_has_default_permissions(admin_request, service_factory):
    service_factory.get('one')
    service_factory.get('one')
    service_factory.get('two')
    service_factory.get('three')

    json_resp = admin_request.get('service.get_services')
    assert len(json_resp['data']) == 3
    assert all(
        set(
            json['permissions']
        ) == set([
            EMAIL_TYPE, SMS_TYPE, INTERNATIONAL_SMS_TYPE,
        ])
        for json in json_resp['data']
    )


def test_get_service_by_id_has_default_service_permissions(admin_request, sample_service):
    json_resp = admin_request.get('service.get_service_by_id', service_id=sample_service.id)

    assert set(
        json_resp['data']['permissions']
    ) == set([
        EMAIL_TYPE, SMS_TYPE, INTERNATIONAL_SMS_TYPE,
    ])


def test_get_service_by_id_should_404_if_no_service(admin_request, notify_db_session):
    json_resp = admin_request.get(
        'service.get_service_by_id',
        service_id=uuid.uuid4(),
        _expected_status=404
    )

    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'No result found'


def test_get_service_by_id_and_user(client, sample_service, sample_user):
    sample_service.reply_to_email = 'something@service.com'
    create_reply_to_email(service=sample_service, email_address='new@service.com')
    auth_header = create_authorization_header()
    resp = client.get(
        '/service/{}?user_id={}'.format(sample_service.id, sample_user.id),
        headers=[auth_header]
    )
    assert resp.status_code == 200
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data']['name'] == sample_service.name
    assert json_resp['data']['id'] == str(sample_service.id)
    assert json_resp['data']['reply_to_email_address'] == 'new@service.com'


def test_get_service_by_id_should_404_if_no_service_for_user(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}?user_id={}'.format(service_id, sample_user.id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_create_service(client, sample_user):
    data = {
        'name': 'created service',
        'user_id': str(sample_user.id),
        'message_limit': 1000,
        'restricted': False,
        'active': False,
        'email_from': 'created.service',
        'created_by': str(sample_user.id)
    }
    auth_header = create_authorization_header()
    headers = [('Content-Type', 'application/json'), auth_header]
    resp = client.post(
        '/service',
        data=json.dumps(data),
        headers=headers)
    json_resp = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == 201
    assert json_resp['data']['id']
    assert json_resp['data']['name'] == 'created service'
    assert json_resp['data']['email_from'] == 'created.service'
    assert not json_resp['data']['research_mode']
    assert json_resp['data']['dvla_organisation'] == '001'
    assert json_resp['data']['sms_sender'] == current_app.config['FROM_NUMBER']
    assert json_resp['data']['rate_limit'] == 3000

    service_db = Service.query.get(json_resp['data']['id'])
    assert service_db.name == 'created service'

    auth_header_fetch = create_authorization_header()

    resp = client.get(
        '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
        headers=[auth_header_fetch]
    )
    assert resp.status_code == 200
    json_resp = json.loads(resp.get_data(as_text=True))
    assert json_resp['data']['name'] == 'created service'
    assert not json_resp['data']['research_mode']

    service_sms_senders = ServiceSmsSender.query.filter_by(service_id=service_db.id).all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == current_app.config['FROM_NUMBER']


def test_should_not_create_service_with_missing_user_id_field(notify_api, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'created_by': str(fake_uuid)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['user_id']


def test_should_error_if_created_by_missing(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'user_id': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['created_by']


def test_should_not_create_service_with_missing_if_user_id_is_not_in_database(notify_api,
                                                                              notify_db,
                                                                              notify_db_session,
                                                                              fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'user_id': fake_uuid,
                'name': 'created service',
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'created_by': str(fake_uuid)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_should_not_create_service_if_missing_data(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'user_id': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['name']
            assert 'Missing data for required field.' in json_resp['message']['message_limit']
            assert 'Missing data for required field.' in json_resp['message']['restricted']


def test_should_not_create_service_with_duplicate_name(notify_api,
                                                       sample_user,
                                                       sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': sample_service.name,
                'user_id': str(sample_service.users[0].id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'sample.service2',
                'created_by': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert "Duplicate service name '{}'".format(sample_service.name) in json_resp['message']['name']


def test_create_service_should_throw_duplicate_key_constraint_for_existing_email_from(notify_api,
                                                                                      service_factory,
                                                                                      sample_user):
    first_service = service_factory.get('First service', email_from='first.service')
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = 'First SERVICE'
            data = {
                'name': service_name,
                'user_id': str(first_service.users[0].id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'first.service',
                'created_by': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert "Duplicate service name '{}'".format(service_name) in json_resp['message']['name']


def test_update_service(client, notify_db, sample_service):
    org = Organisation(colour='#000000', logo='justice-league.png', name='Justice League')
    notify_db.session.add(org)
    notify_db.session.commit()

    auth_header = create_authorization_header()
    resp = client.get(
        '/service/{}'.format(sample_service.id),
        headers=[auth_header]
    )
    json_resp = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == 200
    assert json_resp['data']['name'] == sample_service.name

    data = {
        'name': 'updated service name',
        'email_from': 'updated.service.name',
        'created_by': str(sample_service.created_by.id),
        'organisation': str(org.id),
        'dvla_organisation': DVLA_ORG_LAND_REGISTRY,
        'organisation_type': 'foo',
    }

    auth_header = create_authorization_header()

    resp = client.post(
        '/service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == 200
    assert result['data']['name'] == 'updated service name'
    assert result['data']['email_from'] == 'updated.service.name'
    assert result['data']['organisation'] == str(org.id)
    assert result['data']['dvla_organisation'] == DVLA_ORG_LAND_REGISTRY
    assert result['data']['organisation_type'] == 'foo'


def test_update_service_flags(client, sample_service):
    auth_header = create_authorization_header()
    resp = client.get(
        '/service/{}'.format(sample_service.id),
        headers=[auth_header]
    )
    json_resp = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == 200
    assert json_resp['data']['name'] == sample_service.name
    assert json_resp['data']['research_mode'] is False

    data = {
        'research_mode': True,
        'permissions': [LETTER_TYPE, INTERNATIONAL_SMS_TYPE]
    }

    auth_header = create_authorization_header()

    resp = client.post(
        '/service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == 200
    assert result['data']['research_mode'] is True
    assert set(result['data']['permissions']) == set([LETTER_TYPE, INTERNATIONAL_SMS_TYPE])


@pytest.mark.parametrize("org_type, expected",
                         [("central", True),
                          ('local', False),
                          ("nhs", False)])
def test_update_service_sets_crown(client, sample_service, org_type, expected):
    data = {
        'organisation_type': org_type,
    }
    auth_header = create_authorization_header()

    resp = client.post(
        '/service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))
    assert resp.status_code == 200
    assert result['data']['crown'] is expected


@pytest.fixture(scope='function')
def service_with_no_permissions(notify_db, notify_db_session):
    return create_service(service_permissions=[])


def test_update_service_flags_with_service_without_default_service_permissions(client, service_with_no_permissions):
    auth_header = create_authorization_header()
    data = {
        'permissions': [LETTER_TYPE, INTERNATIONAL_SMS_TYPE],
    }

    resp = client.post(
        '/service/{}'.format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 200
    assert set(result['data']['permissions']) == set([LETTER_TYPE, INTERNATIONAL_SMS_TYPE])


def test_update_service_flags_will_remove_service_permissions(client, notify_db, notify_db_session):
    auth_header = create_authorization_header()

    service = create_service(service_permissions=[SMS_TYPE, EMAIL_TYPE, INTERNATIONAL_SMS_TYPE])

    assert INTERNATIONAL_SMS_TYPE in [p.permission for p in service.permissions]

    data = {
        'permissions': [SMS_TYPE, EMAIL_TYPE]
    }

    resp = client.post(
        '/service/{}'.format(service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 200
    assert INTERNATIONAL_SMS_TYPE not in result['data']['permissions']

    permissions = ServicePermission.query.filter_by(service_id=service.id).all()
    assert set([p.permission for p in permissions]) == set([SMS_TYPE, EMAIL_TYPE])


def test_update_permissions_will_override_permission_flags(client, service_with_no_permissions):
    auth_header = create_authorization_header()

    data = {
        'permissions': [LETTER_TYPE, INTERNATIONAL_SMS_TYPE]
    }

    resp = client.post(
        '/service/{}'.format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 200
    assert set(result['data']['permissions']) == set([LETTER_TYPE, INTERNATIONAL_SMS_TYPE])


def test_update_service_permissions_will_add_service_permissions(client, sample_service):
    auth_header = create_authorization_header()

    data = {
        'permissions': [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE]
    }

    resp = client.post(
        '/service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 200
    assert set(result['data']['permissions']) == set([SMS_TYPE, EMAIL_TYPE, LETTER_TYPE])


@pytest.mark.parametrize(
    'permission_to_add',
    [
        (EMAIL_TYPE),
        (SMS_TYPE),
        (INTERNATIONAL_SMS_TYPE),
        (LETTER_TYPE),
        (INBOUND_SMS_TYPE),
    ]
)
def test_add_service_permission_will_add_permission(client, service_with_no_permissions, permission_to_add):
    auth_header = create_authorization_header()

    data = {
        'permissions': [permission_to_add]
    }

    resp = client.post(
        '/service/{}'.format(service_with_no_permissions.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )

    permissions = ServicePermission.query.filter_by(service_id=service_with_no_permissions.id).all()

    assert resp.status_code == 200
    assert [p.permission for p in permissions] == [permission_to_add]


def test_update_permissions_with_an_invalid_permission_will_raise_error(client, sample_service):
    auth_header = create_authorization_header()
    invalid_permission = 'invalid_permission'

    data = {
        'permissions': [EMAIL_TYPE, SMS_TYPE, invalid_permission]
    }

    resp = client.post(
        '/service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 400
    assert result['result'] == 'error'
    assert "Invalid Service Permission: '{}'".format(invalid_permission) in result['message']['permissions']


def test_update_permissions_with_duplicate_permissions_will_raise_error(client, sample_service):
    auth_header = create_authorization_header()

    data = {
        'permissions': [EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, LETTER_TYPE]
    }

    resp = client.post(
        '/service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[('Content-Type', 'application/json'), auth_header]
    )
    result = json.loads(resp.get_data(as_text=True))

    assert resp.status_code == 400
    assert result['result'] == 'error'
    assert "Duplicate Service Permission: ['{}']".format(LETTER_TYPE) in result['message']['permissions']


def test_update_service_research_mode_throws_validation_error(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name
            assert not json_resp['data']['research_mode']

            data = {
                'research_mode': "dedede"
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert result['message']['research_mode'][0] == "Not a valid boolean."
            assert resp.status_code == 400


def test_should_not_update_service_with_duplicate_name(notify_api,
                                                       notify_db,
                                                       notify_db_session,
                                                       sample_user,
                                                       sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_name = "another name"
            service = create_service(
                service_name=service_name,
                user=sample_user,
                email_from='another.name')
            data = {
                'name': service_name,
                'created_by': str(service.created_by.id)
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert "Duplicate service name '{}'".format(service_name) in json_resp['message']['name']


def test_should_not_update_service_with_duplicate_email_from(notify_api,
                                                             notify_db,
                                                             notify_db_session,
                                                             sample_user,
                                                             sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            email_from = "duplicate.name"
            service_name = "duplicate name"
            service = create_service(
                service_name=service_name,
                user=sample_user,
                email_from=email_from)
            data = {
                'name': service_name,
                'email_from': email_from,
                'created_by': str(service.created_by.id)
            }

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 400
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert (
                "Duplicate service name '{}'".format(service_name) in json_resp['message']['name'] or
                "Duplicate service name '{}'".format(email_from) in json_resp['message']['name']
            )


def test_update_service_should_404_if_id_is_invalid(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'updated service name'
            }

            missing_service_id = uuid.uuid4()

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}'.format(missing_service_id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 404


def test_get_users_by_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_on_service = sample_service.users[0]
            auth_header = create_authorization_header()

            resp = client.get(
                '/service/{}/users'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )

            assert resp.status_code == 200
            result = json.loads(resp.get_data(as_text=True))
            assert len(result['data']) == 1
            assert result['data'][0]['name'] == user_on_service.name
            assert result['data'][0]['email_address'] == user_on_service.email_address
            assert result['data'][0]['mobile_number'] == user_on_service.mobile_number


def test_get_users_for_service_returns_empty_list_if_no_users_associated_with_service(notify_api,
                                                                                      sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            dao_remove_user_from_service(sample_service, sample_service.users[0])
            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/users'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert result['data'] == []


def test_get_users_for_service_returns_404_when_service_does_not_exist(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = uuid.uuid4()
            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/users'.format(service_id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert response.status_code == 404
            result = json.loads(response.get_data(as_text=True))
            assert result['result'] == 'error'
            assert result['message'] == 'No result found'


def test_default_permissions_are_added_for_user_service(notify_api,
                                                        notify_db,
                                                        notify_db_session,
                                                        sample_service,
                                                        sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'created service',
                'user_id': str(sample_user.id),
                'message_limit': 1000,
                'restricted': False,
                'active': False,
                'email_from': 'created.service',
                'created_by': str(sample_user.id)
            }
            auth_header = create_authorization_header()
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 201
            assert json_resp['data']['id']
            assert json_resp['data']['name'] == 'created service'
            assert json_resp['data']['email_from'] == 'created.service'

            auth_header_fetch = create_authorization_header()

            resp = client.get(
                '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
                headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            header = create_authorization_header()
            response = client.get(
                url_for('user.get_user', user_id=sample_user.id),
                headers=[header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            service_permissions = json_resp['data']['permissions'][str(sample_service.id)]
            from app.dao.permissions_dao import default_service_permissions
            assert sorted(default_service_permissions) == sorted(service_permissions)


def test_add_existing_user_to_another_service_with_all_permissions(notify_api,
                                                                   notify_db,
                                                                   notify_db_session,
                                                                   sample_service,
                                                                   sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # check which users part of service
            user_already_in_service = sample_service.users[0]
            auth_header = create_authorization_header()

            resp = client.get(
                '/service/{}/users'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header]
            )

            assert resp.status_code == 200
            result = json.loads(resp.get_data(as_text=True))
            assert len(result['data']) == 1
            assert result['data'][0]['email_address'] == user_already_in_service.email_address

            # add new user to service
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            # they must exist in db first
            save_model_user(user_to_add)

            data = [{"permission": "send_emails"},
                    {"permission": "send_letters"},
                    {"permission": "send_texts"},
                    {"permission": "manage_users"},
                    {"permission": "manage_settings"},
                    {"permission": "manage_api_keys"},
                    {"permission": "manage_templates"},
                    {"permission": "view_activity"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check new user added to service
            auth_header = create_authorization_header()

            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert str(user_to_add.id) in json_resp['data']['users']

            # check user has all permissions
            auth_header = create_authorization_header()
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['send_texts', 'send_emails', 'send_letters', 'manage_users',
                                    'manage_settings', 'manage_templates', 'manage_api_keys', 'view_activity']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_send_permissions(notify_api,
                                                                    notify_db,
                                                                    notify_db_session,
                                                                    sample_service,
                                                                    sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            data = [{"permission": "send_emails"},
                    {"permission": "send_letters"},
                    {"permission": "send_texts"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header()
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['send_texts', 'send_emails', 'send_letters']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_manage_permissions(notify_api,
                                                                      notify_db,
                                                                      notify_db_session,
                                                                      sample_service,
                                                                      sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            data = [{"permission": "manage_users"},
                    {"permission": "manage_settings"},
                    {"permission": "manage_templates"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header()
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['manage_users', 'manage_settings', 'manage_templates']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_another_service_with_manage_api_keys(notify_api,
                                                                   notify_db,
                                                                   notify_db_session,
                                                                   sample_service,
                                                                   sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            # they must exist in db first
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            data = [{"permission": "manage_api_keys"}]

            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            assert resp.status_code == 201

            # check user has send permissions
            auth_header = create_authorization_header()
            resp = client.get(url_for('user.get_user', user_id=user_to_add.id),
                              headers=[('Content-Type', 'application/json'), auth_header])

            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))

            permissions = json_resp['data']['permissions'][str(sample_service.id)]
            expected_permissions = ['manage_api_keys']
            assert sorted(expected_permissions) == sorted(permissions)


def test_add_existing_user_to_non_existing_service_returns404(notify_api,
                                                              notify_db,
                                                              notify_db_session,
                                                              sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            user_to_add = User(
                name='Invited User',
                email_address='invited@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+4477123456'
            )
            save_model_user(user_to_add)

            incorrect_id = uuid.uuid4()

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(incorrect_id, user_to_add.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'No result found'

            assert resp.status_code == 404
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_add_existing_user_of_service_to_service_returns400(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            existing_user_id = sample_service.users[0].id

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, existing_user_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'User id: {} already part of service id: {}'.format(existing_user_id, sample_service.id)

            assert resp.status_code == 400
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_add_unknown_user_to_service_returns404(notify_api, notify_db, notify_db_session, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            incorrect_id = 9876

            data = {'permissions': ['send_messages', 'manage_service', 'manage_api_keys']}
            auth_header = create_authorization_header()

            resp = client.post(
                '/service/{}/users/{}'.format(sample_service.id, incorrect_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=json.dumps(data)
            )

            result = json.loads(resp.get_data(as_text=True))
            expected_message = 'No result found'

            assert resp.status_code == 404
            assert result['result'] == 'error'
            assert result['message'] == expected_message


def test_remove_user_from_service(
        notify_db, notify_db_session, client, sample_user_service_permission
):
    second_user = create_user(email="new@digital.cabinet-office.gov.uk")
    # Simulates successfully adding a user to the service
    second_permission = create_user_service_permission(
        notify_db,
        notify_db_session,
        user=second_user)
    endpoint = url_for(
        'service.remove_user_from_service',
        service_id=str(second_permission.service.id),
        user_id=str(second_permission.user.id))
    auth_header = create_authorization_header()
    resp = client.delete(
        endpoint,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 204


def test_remove_non_existant_user_from_service(
        client, sample_user_service_permission
):
    second_user = create_user(email="new@digital.cabinet-office.gov.uk")
    endpoint = url_for(
        'service.remove_user_from_service',
        service_id=str(sample_user_service_permission.service.id),
        user_id=str(second_user.id))
    auth_header = create_authorization_header()
    resp = client.delete(
        endpoint,
        headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 404


def test_cannot_remove_only_user_from_service(notify_api,
                                              notify_db,
                                              notify_db_session,
                                              sample_user_service_permission):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            endpoint = url_for(
                'service.remove_user_from_service',
                service_id=str(sample_user_service_permission.service.id),
                user_id=str(sample_user_service_permission.user.id))
            auth_header = create_authorization_header()
            resp = client.delete(
                endpoint,
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 400
            result = json.loads(resp.get_data(as_text=True))
            assert result['message'] == 'You cannot remove the only user for a service'


# This test is just here verify get_service_and_api_key_history that is a temp solution
# until proper ui is sorted out on admin app
def test_get_service_and_api_key_history(notify_api, notify_db, notify_db_session, sample_service):
    from tests.app.conftest import sample_api_key as create_sample_api_key
    api_key = create_sample_api_key(notify_db, notify_db_session, service=sample_service)

    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header()
            response = client.get(
                path='/service/{}/history'.format(sample_service.id),
                headers=[auth_header]
            )
            assert response.status_code == 200

            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['data']['service_history'][0]['id'] == str(sample_service.id)
            assert json_resp['data']['api_key_history'][0]['id'] == str(api_key.id)


def test_get_all_notifications_for_service_in_order(notify_api, notify_db, notify_db_session):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        service_1 = create_service(service_name="1", email_from='1')
        service_2 = create_service(service_name="2", email_from='2')

        create_sample_notification(notify_db, notify_db_session, service=service_2)

        notification_1 = create_sample_notification(notify_db, notify_db_session, service=service_1)
        notification_2 = create_sample_notification(notify_db, notify_db_session, service=service_1)
        notification_3 = create_sample_notification(notify_db, notify_db_session, service=service_1)

        auth_header = create_authorization_header()

        response = client.get(
            path='/service/{}/notifications'.format(service_1.id),
            headers=[auth_header])

        resp = json.loads(response.get_data(as_text=True))
        assert len(resp['notifications']) == 3
        assert resp['notifications'][0]['to'] == notification_3.to
        assert resp['notifications'][1]['to'] == notification_2.to
        assert resp['notifications'][2]['to'] == notification_1.to
        assert response.status_code == 200


def test_get_notification_for_service_without_uuid(client, notify_db, notify_db_session):
    service_1 = create_service(service_name="1", email_from='1')
    response = client.get(
        path='/service/{}/notifications/{}'.format(service_1.id, 'foo'),
        headers=[create_authorization_header()]
    )
    assert response.status_code == 404


def test_get_notification_for_service(client, notify_db, notify_db_session):

    service_1 = create_service(service_name="1", email_from='1')
    service_2 = create_service(service_name="2", email_from='2')

    service_1_notifications = [
        create_sample_notification(notify_db, notify_db_session, service=service_1),
        create_sample_notification(notify_db, notify_db_session, service=service_1),
        create_sample_notification(notify_db, notify_db_session, service=service_1),
    ]

    create_sample_notification(notify_db, notify_db_session, service=service_2)

    for notification in service_1_notifications:
        response = client.get(
            path='/service/{}/notifications/{}'.format(service_1.id, notification.id),
            headers=[create_authorization_header()]
        )
        resp = json.loads(response.get_data(as_text=True))
        assert str(resp['id']) == str(notification.id)
        assert response.status_code == 200

        service_2_response = client.get(
            path='/service/{}/notifications/{}'.format(service_2.id, notification.id),
            headers=[create_authorization_header()]
        )
        assert service_2_response.status_code == 404
        service_2_response = json.loads(service_2_response.get_data(as_text=True))
        assert service_2_response == {'message': 'No result found', 'result': 'error'}


def test_get_notification_for_service_includes_created_by(admin_request, sample_notification):
    user = sample_notification.created_by = sample_notification.service.created_by

    resp = admin_request.get(
        'service.get_notification_for_service',
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id
    )

    assert resp['id'] == str(sample_notification.id)
    assert resp['created_by'] == {
        'id': str(user.id),
        'name': user.name,
        'email_address': user.email_address
    }


def test_get_notification_for_service_returns_old_template_version(admin_request, sample_template):
    sample_notification = create_notification(sample_template)
    sample_notification.reference = 'modified-inplace'
    sample_template.version = 2
    sample_template.content = 'New template content'

    resp = admin_request.get(
        'service.get_notification_for_service',
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id
    )

    assert resp['reference'] == 'modified-inplace'
    assert resp['template']['version'] == 1
    assert resp['template']['content'] == sample_notification.template.content
    assert resp['template']['content'] != sample_template.content


@pytest.mark.parametrize(
    'include_from_test_key, expected_count_of_notifications',
    [
        (False, 2),
        (True, 3)
    ]
)
def test_get_all_notifications_for_service_including_ones_made_by_jobs(
        client,
        notify_db,
        notify_db_session,
        sample_service,
        include_from_test_key,
        expected_count_of_notifications
):
    with_job = sample_notification_with_job(notify_db, notify_db_session, service=sample_service)
    without_job = create_sample_notification(notify_db, notify_db_session, service=sample_service)
    # from_test_api_key
    create_sample_notification(
        notify_db, notify_db_session, service=sample_service, key_type=KEY_TYPE_TEST
    )

    auth_header = create_authorization_header()

    response = client.get(
        path='/service/{}/notifications?include_from_test_key={}'.format(
            sample_service.id, include_from_test_key
        ),
        headers=[auth_header]
    )

    resp = json.loads(response.get_data(as_text=True))
    assert len(resp['notifications']) == expected_count_of_notifications
    assert resp['notifications'][0]['to'] == with_job.to
    assert resp['notifications'][1]['to'] == without_job.to
    assert response.status_code == 200


def test_get_only_api_created_notifications_for_service(
    admin_request,
    sample_job,
    sample_template
):
    create_notification(sample_template, job=sample_job)
    without_job = create_notification(sample_template)

    resp = admin_request.get(
        'service.get_all_notifications_for_service',
        service_id=sample_template.service_id,
        include_jobs=False
    )
    assert len(resp['notifications']) == 1
    assert resp['notifications'][0]['id'] == str(without_job.id)


@pytest.mark.parametrize('should_prefix', [
    True,
    False,
])
def test_prefixing_messages_based_on_prefix_sms(
    client,
    notify_db_session,
    should_prefix,
):
    service = create_service(
        prefix_sms=should_prefix
    )

    result = client.get(
        url_for(
            'service.get_service_by_id',
            service_id=service.id
        ),
        headers=[('Content-Type', 'application/json'), create_authorization_header()]
    )
    service = json.loads(result.get_data(as_text=True))['data']
    assert service['prefix_sms'] == should_prefix


@pytest.mark.parametrize('posted_value, stored_value, returned_value', [
    (True, True, True),
    (False, False, False),
])
def test_set_sms_prefixing_for_service(
    admin_request,
    client,
    sample_service,
    posted_value,
    stored_value,
    returned_value,
):
    result = admin_request.post(
        'service.update_service',
        service_id=sample_service.id,
        _data={'prefix_sms': posted_value},
    )
    assert result['data']['prefix_sms'] == stored_value
    assert result['data']['sms_sender'] == current_app.config['FROM_NUMBER']


def test_set_sms_prefixing_for_service_cant_be_none(
    admin_request,
    sample_service,
):
    resp = admin_request.post(
        'service.update_service',
        service_id=sample_service.id,
        _data={'prefix_sms': None},
        _expected_status=400,
    )
    assert resp['message'] == {'prefix_sms': ['Field may not be null.']}


@pytest.mark.parametrize('today_only,stats', [
    ('False', {'requested': 2, 'delivered': 1, 'failed': 0}),
    ('True', {'requested': 1, 'delivered': 0, 'failed': 0})
], ids=['seven_days', 'today'])
def test_get_detailed_service(notify_db, notify_db_session, notify_api, sample_service, today_only, stats):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        with freeze_time('2000-01-01T12:00:00'):
            create_sample_notification(notify_db, notify_db_session, status='delivered')
        with freeze_time('2000-01-02T12:00:00'):
            create_sample_notification(notify_db, notify_db_session, status='created')
            resp = client.get(
                '/service/{}?detailed=True&today_only={}'.format(sample_service.id, today_only),
                headers=[create_authorization_header()]
            )

    assert resp.status_code == 200
    service = json.loads(resp.get_data(as_text=True))['data']
    assert service['id'] == str(sample_service.id)
    assert 'statistics' in service.keys()
    assert set(service['statistics'].keys()) == {SMS_TYPE, EMAIL_TYPE, LETTER_TYPE}
    assert service['statistics'][SMS_TYPE] == stats


@pytest.mark.parametrize(
    'url, expected_status, expected_json', [
        (
            '/service/{}/notifications/monthly?year=2001',
            200,
            {'data': {'foo': 'bar'}},
        ),
        (
            '/service/{}/notifications/monthly?year=baz',
            400,
            {'message': 'Year must be a number', 'result': 'error'},
        ),
        (
            '/service/{}/notifications/monthly',
            400,
            {'message': 'Year must be a number', 'result': 'error'},
        ),
    ]
)
def test_get_monthly_notification_stats(mocker, client, sample_service, url, expected_status, expected_json):
    mocker.patch(
        'app.service.rest.dao_fetch_monthly_historical_stats_for_service',
        return_value={'foo': 'bar'},
    )
    response = client.get(
        url.format(sample_service.id),
        headers=[create_authorization_header()]
    )
    assert response.status_code == expected_status
    assert json.loads(response.get_data(as_text=True)) == expected_json


def test_get_services_with_detailed_flag(client, notify_db, notify_db_session):
    notifications = [
        create_sample_notification(notify_db, notify_db_session),
        create_sample_notification(notify_db, notify_db_session),
        create_sample_notification(notify_db, notify_db_session, key_type=KEY_TYPE_TEST)
    ]
    resp = client.get(
        '/service?detailed=True',
        headers=[create_authorization_header()]
    )

    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))['data']
    assert len(data) == 1
    assert data[0]['name'] == 'Sample service'
    assert data[0]['id'] == str(notifications[0].service_id)
    assert data[0]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 3},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }


def test_get_services_with_detailed_flag_excluding_from_test_key(notify_api, notify_db, notify_db_session):
    create_sample_notification(notify_db, notify_db_session, key_type=KEY_TYPE_NORMAL),
    create_sample_notification(notify_db, notify_db_session, key_type=KEY_TYPE_TEAM),
    create_sample_notification(notify_db, notify_db_session, key_type=KEY_TYPE_TEST),
    create_sample_notification(notify_db, notify_db_session, key_type=KEY_TYPE_TEST),
    create_sample_notification(notify_db, notify_db_session, key_type=KEY_TYPE_TEST)

    with notify_api.test_request_context(), notify_api.test_client() as client:
        resp = client.get(
            '/service?detailed=True&include_from_test_key=False',
            headers=[create_authorization_header()]
        )

    assert resp.status_code == 200
    data = json.loads(resp.get_data(as_text=True))['data']
    assert len(data) == 1
    assert data[0]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 2},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }


def test_get_services_with_detailed_flag_accepts_date_range(client, mocker):
    mock_get_detailed_services = mocker.patch('app.service.rest.get_detailed_services', return_value={})
    resp = client.get(
        url_for('service.get_services', detailed=True, start_date='2001-01-01', end_date='2002-02-02'),
        headers=[create_authorization_header()]
    )

    mock_get_detailed_services.assert_called_once_with(
        start_date=date(2001, 1, 1),
        end_date=date(2002, 2, 2),
        only_active=ANY,
        include_from_test_key=ANY
    )
    assert resp.status_code == 200


@freeze_time('2002-02-02')
def test_get_services_with_detailed_flag_defaults_to_today(client, mocker):
    mock_get_detailed_services = mocker.patch('app.service.rest.get_detailed_services', return_value={})
    resp = client.get(
        url_for('service.get_services', detailed=True),
        headers=[create_authorization_header()]
    )

    mock_get_detailed_services.assert_called_once_with(
        end_date=date(2002, 2, 2),
        include_from_test_key=ANY,
        only_active=ANY,
        start_date=date(2002, 2, 2)
    )

    assert resp.status_code == 200


def test_get_detailed_services_groups_by_service(notify_db, notify_db_session):
    from app.service.rest import get_detailed_services

    service_1 = create_service(service_name="1", email_from='1')
    service_2 = create_service(service_name="2", email_from='2')

    create_sample_notification(notify_db, notify_db_session, service=service_1, status='created')
    create_sample_notification(notify_db, notify_db_session, service=service_2, status='created')
    create_sample_notification(notify_db, notify_db_session, service=service_1, status='delivered')
    create_sample_notification(notify_db, notify_db_session, service=service_1, status='created')

    data = get_detailed_services(start_date=datetime.utcnow().date(), end_date=datetime.utcnow().date())
    data = sorted(data, key=lambda x: x['name'])

    assert len(data) == 2
    assert data[0]['id'] == str(service_1.id)
    assert data[0]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 1, 'failed': 0, 'requested': 3},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }
    assert data[1]['id'] == str(service_2.id)
    assert data[1]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 1},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }


def test_get_detailed_services_includes_services_with_no_notifications(notify_db, notify_db_session):
    from app.service.rest import get_detailed_services

    service_1 = create_service(service_name="1", email_from='1')
    service_2 = create_service(service_name="2", email_from='2')

    create_sample_notification(notify_db, notify_db_session, service=service_1)

    data = get_detailed_services(start_date=datetime.utcnow().date(),
                                 end_date=datetime.utcnow().date())
    data = sorted(data, key=lambda x: x['name'])

    assert len(data) == 2
    assert data[0]['id'] == str(service_1.id)
    assert data[0]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 1},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }
    assert data[1]['id'] == str(service_2.id)
    assert data[1]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }


def test_get_detailed_services_only_includes_todays_notifications(notify_db, notify_db_session):
    from app.service.rest import get_detailed_services

    create_sample_notification(notify_db, notify_db_session, created_at=datetime(2015, 10, 9, 23, 59))
    create_sample_notification(notify_db, notify_db_session, created_at=datetime(2015, 10, 10, 0, 0))
    create_sample_notification(notify_db, notify_db_session, created_at=datetime(2015, 10, 10, 12, 0))

    with freeze_time('2015-10-10T12:00:00'):
        data = get_detailed_services(start_date=datetime.utcnow().date(), end_date=datetime.utcnow().date())
        data = sorted(data, key=lambda x: x['id'])

    assert len(data) == 1
    assert data[0]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 2},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }


@pytest.mark.parametrize(
    'set_time',
    ['2017-03-28T12:00:00', '2017-01-28T12:00:00', '2017-01-02T12:00:00', '2017-10-31T12:00:00']
)
def test_get_detailed_services_for_date_range(notify_db, notify_db_session, set_time):
    from app.service.rest import get_detailed_services

    with freeze_time(set_time):
        create_sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow() - timedelta(days=3))
        create_sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow() - timedelta(days=2))
        create_sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow() - timedelta(days=1))
        create_sample_notification(notify_db, notify_db_session, created_at=datetime.utcnow())

        start_date = (datetime.utcnow() - timedelta(days=2)).date()
        end_date = (datetime.utcnow() - timedelta(days=1)).date()

    data = get_detailed_services(only_active=False, include_from_test_key=True,
                                 start_date=start_date, end_date=end_date)

    assert len(data) == 1
    assert data[0]['statistics'] == {
        EMAIL_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0},
        SMS_TYPE: {'delivered': 0, 'failed': 0, 'requested': 2},
        LETTER_TYPE: {'delivered': 0, 'failed': 0, 'requested': 0}
    }


@pytest.mark.parametrize('query_string, expected_status, expected_json', [
    ('', 200, {'data': {'email_count': 0, 'sms_count': 0}}),
    ('?year=2000', 200, {'data': {'email_count': 0, 'sms_count': 0}}),
    ('?year=abcd', 400, {'message': 'Year must be a number', 'result': 'error'}),
])
def test_get_service_provider_aggregate_statistics(
        client,
        sample_service,
        query_string,
        expected_status,
        expected_json,
):
    response = client.get(
        '/service/{}/fragment/aggregate_statistics{}'.format(sample_service.id, query_string),
        headers=[create_authorization_header()]
    )
    assert response.status_code == expected_status
    assert json.loads(response.get_data(as_text=True)) == expected_json


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_correct_data(
        notify_db,
        notify_db_session,
        client,
        sample_template
):

    # add a historical notification for template
    not1 = create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2016, 4, 1),
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='sending'
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='permanent-failure'
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='temporary-failure'
    )

    daily_stats_template_usage_by_month()

    create_notification(
        sample_template,
        created_at=datetime.utcnow()
    )

    resp = client.get(
        '/service/{}/notifications/templates_usage/monthly?year=2017'.format(not1.service_id),
        headers=[create_authorization_header()]
    )
    resp_json = json.loads(resp.get_data(as_text=True)).get('stats')

    assert resp.status_code == 200
    assert len(resp_json) == 2

    assert resp_json[0]["template_id"] == str(sample_template.id)
    assert resp_json[0]["name"] == sample_template.name
    assert resp_json[0]["type"] == sample_template.template_type
    assert resp_json[0]["month"] == 4
    assert resp_json[0]["year"] == 2017
    assert resp_json[0]["count"] == 3

    assert resp_json[1]["template_id"] == str(sample_template.id)
    assert resp_json[1]["name"] == sample_template.name
    assert resp_json[1]["type"] == sample_template.template_type
    assert resp_json[1]["month"] == 11
    assert resp_json[1]["year"] == 2017
    assert resp_json[1]["count"] == 1


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_no_data(
        notify_db,
        notify_db_session,
        client,
        sample_template
):

    # add a historical notification for template
    not1 = create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2016, 4, 1),
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='sending'
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='permanent-failure'
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='temporary-failure'
    )

    daily_stats_template_usage_by_month()

    create_notification(
        sample_template,
        created_at=datetime.utcnow()
    )

    resp = client.get(
        '/service/{}/notifications/templates_usage/monthly?year=2015'.format(not1.service_id),
        headers=[create_authorization_header()]
    )
    resp_json = json.loads(resp.get_data(as_text=True)).get('stats')

    assert resp.status_code == 200
    assert len(resp_json) == 0


@freeze_time('2017-11-11 02:00')
def test_get_template_usage_by_month_returns_two_templates(
        notify_db,
        notify_db_session,
        client,
        sample_template,
        sample_service
):

    template_one = create_template(sample_service)

    # add a historical notification for template
    not1 = create_notification_history(
        notify_db,
        notify_db_session,
        template_one,
        created_at=datetime(2017, 4, 1),
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='sending'
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='permanent-failure'
    )

    create_notification_history(
        notify_db,
        notify_db_session,
        sample_template,
        created_at=datetime(2017, 4, 1),
        status='temporary-failure'
    )

    daily_stats_template_usage_by_month()

    create_notification(
        sample_template,
        created_at=datetime.utcnow()
    )

    resp = client.get(
        '/service/{}/notifications/templates_usage/monthly?year=2017'.format(not1.service_id),
        headers=[create_authorization_header()]
    )
    resp_json = json.loads(resp.get_data(as_text=True)).get('stats')

    assert resp.status_code == 200
    assert len(resp_json) == 3

    resp_json = sorted(resp_json, key=lambda k: (k.get('year', 0), k.get('month', 0), k.get('count', 0)))

    assert resp_json[0]["template_id"] == str(template_one.id)
    assert resp_json[0]["name"] == template_one.name
    assert resp_json[0]["type"] == template_one.template_type
    assert resp_json[0]["month"] == 4
    assert resp_json[0]["year"] == 2017
    assert resp_json[0]["count"] == 1

    assert resp_json[1]["template_id"] == str(sample_template.id)
    assert resp_json[1]["name"] == sample_template.name
    assert resp_json[1]["type"] == sample_template.template_type
    assert resp_json[1]["month"] == 4
    assert resp_json[1]["year"] == 2017
    assert resp_json[1]["count"] == 3

    assert resp_json[2]["template_id"] == str(sample_template.id)
    assert resp_json[2]["name"] == sample_template.name
    assert resp_json[2]["type"] == sample_template.template_type
    assert resp_json[2]["month"] == 11
    assert resp_json[2]["year"] == 2017
    assert resp_json[2]["count"] == 1


def test_search_for_notification_by_to_field(client, notify_db, notify_db_session):
    create_notification = partial(create_sample_notification, notify_db, notify_db_session)
    notification1 = create_notification(to_field='+447700900855', normalised_to='447700900855')
    notification2 = create_notification(to_field='jack@gmail.com', normalised_to='jack@gmail.com')

    response = client.get(
        '/service/{}/notifications?to={}'.format(notification1.service_id, 'jack@gmail.com'),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']

    assert response.status_code == 200
    assert len(notifications) == 1
    assert str(notification2.id) == notifications[0]['id']


def test_search_for_notification_by_to_field_return_empty_list_if_there_is_no_match(
    client, notify_db, notify_db_session
):
    create_notification = partial(create_sample_notification, notify_db, notify_db_session)
    notification1 = create_notification(to_field='+447700900855')
    create_notification(to_field='jack@gmail.com')

    response = client.get(
        '/service/{}/notifications?to={}'.format(notification1.service_id, '+447700900800'),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']

    assert response.status_code == 200
    assert len(notifications) == 0


def test_search_for_notification_by_to_field_return_multiple_matches(client, notify_db, notify_db_session):
    create_notification = partial(create_sample_notification, notify_db, notify_db_session)
    notification1 = create_notification(to_field='+447700900855', normalised_to='447700900855')
    notification2 = create_notification(to_field=' +44 77009 00855 ', normalised_to='447700900855')
    notification3 = create_notification(to_field='+44770 0900 855', normalised_to='447700900855')
    notification4 = create_notification(to_field='jack@gmail.com', normalised_to='jack@gmail.com')

    response = client.get(
        '/service/{}/notifications?to={}'.format(notification1.service_id, '+447700900855'),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']
    notification_ids = [notification['id'] for notification in notifications]

    assert response.status_code == 200
    assert len(notifications) == 3

    assert str(notification1.id) in notification_ids
    assert str(notification2.id) in notification_ids
    assert str(notification3.id) in notification_ids
    assert str(notification4.id) not in notification_ids


def test_update_service_calls_send_notification_as_service_becomes_live(notify_db, notify_db_session, client, mocker):
    send_notification_mock = mocker.patch('app.service.rest.send_notification_to_service_users')

    restricted_service = create_service(restricted=True)

    data = {
        "restricted": False
    }

    auth_header = create_authorization_header()
    resp = client.post(
        'service/{}'.format(restricted_service.id),
        data=json.dumps(data),
        headers=[auth_header],
        content_type='application/json'
    )

    assert resp.status_code == 200
    send_notification_mock.assert_called_once_with(
        service_id=restricted_service.id,
        template_id='618185c6-3636-49cd-b7d2-6f6f5eb3bdde',
        personalisation={
            'service_name': restricted_service.name,
            'message_limit': '1,000'
        },
        include_user_fields=['name']
    )


def test_update_service_does_not_call_send_notification_for_live_service(sample_service, client, mocker):
    send_notification_mock = mocker.patch('app.service.rest.send_notification_to_service_users')

    data = {
        "restricted": True
    }

    auth_header = create_authorization_header()
    resp = client.post(
        'service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[auth_header],
        content_type='application/json'
    )

    assert resp.status_code == 200
    assert not send_notification_mock.called


def test_update_service_does_not_call_send_notification_when_restricted_not_changed(sample_service, client, mocker):
    send_notification_mock = mocker.patch('app.service.rest.send_notification_to_service_users')

    data = {
        "name": 'Name of service'
    }

    auth_header = create_authorization_header()
    resp = client.post(
        'service/{}'.format(sample_service.id),
        data=json.dumps(data),
        headers=[auth_header],
        content_type='application/json'
    )

    assert resp.status_code == 200
    assert not send_notification_mock.called


def test_search_for_notification_by_to_field_filters_by_status(client, notify_db, notify_db_session):
    create_notification = partial(
        create_sample_notification,
        notify_db,
        notify_db_session,
        to_field='+447700900855',
        normalised_to='447700900855'
    )
    notification1 = create_notification(status='delivered')
    create_notification(status='sending')

    response = client.get(
        '/service/{}/notifications?to={}&status={}'.format(
            notification1.service_id, '+447700900855', 'delivered'
        ),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']
    notification_ids = [notification['id'] for notification in notifications]

    assert response.status_code == 200
    assert len(notifications) == 1
    assert str(notification1.id) in notification_ids


def test_search_for_notification_by_to_field_filters_by_statuses(client, notify_db, notify_db_session):
    create_notification = partial(
        create_sample_notification,
        notify_db,
        notify_db_session,
        to_field='+447700900855',
        normalised_to='447700900855'
    )
    notification1 = create_notification(status='delivered')
    notification2 = create_notification(status='sending')

    response = client.get(
        '/service/{}/notifications?to={}&status={}&status={}'.format(
            notification1.service_id, '+447700900855', 'delivered', 'sending'
        ),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']
    notification_ids = [notification['id'] for notification in notifications]

    assert response.status_code == 200
    assert len(notifications) == 2
    assert str(notification1.id) in notification_ids
    assert str(notification2.id) in notification_ids


def test_search_for_notification_by_to_field_returns_content(
    client,
    notify_db,
    notify_db_session,
    sample_template_with_placeholders
):
    notification = create_sample_notification(
        notify_db,
        notify_db_session,
        to_field='+447700900855',
        normalised_to='447700900855',
        template=sample_template_with_placeholders,
        personalisation={"name": "Foo"}
    )

    response = client.get(
        '/service/{}/notifications?to={}'.format(
            sample_template_with_placeholders.service_id, '+447700900855'
        ),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']
    assert response.status_code == 200
    assert len(notifications) == 1

    assert notifications[0]['id'] == str(notification.id)
    assert notifications[0]['to'] == '+447700900855'
    assert notifications[0]['template']['content'] == 'Hello (( Name))\nYour thing is due soon'


def test_send_one_off_notification(sample_service, admin_request, mocker):
    template = create_template(service=sample_service)
    mocker.patch('app.service.send_notification.send_notification_to_queue')

    response = admin_request.post(
        'service.create_one_off_notification',
        service_id=sample_service.id,
        _data={
            'template_id': str(template.id),
            'to': '07700900001',
            'created_by': str(sample_service.created_by_id)
        },
        _expected_status=201
    )

    noti = Notification.query.one()
    assert response['id'] == str(noti.id)


def test_get_notification_for_service_includes_template_redacted(admin_request, sample_notification):
    resp = admin_request.get(
        'service.get_notification_for_service',
        service_id=sample_notification.service_id,
        notification_id=sample_notification.id
    )

    assert resp['id'] == str(sample_notification.id)
    assert resp['template']['redact_personalisation'] is False


def test_get_all_notifications_for_service_includes_template_redacted(admin_request, sample_service):
    normal_template = create_template(sample_service)

    redacted_template = create_template(sample_service)
    dao_redact_template(redacted_template, sample_service.created_by_id)

    with freeze_time('2000-01-01'):
        redacted_noti = create_notification(redacted_template)
    with freeze_time('2000-01-02'):
        normal_noti = create_notification(normal_template)

    resp = admin_request.get(
        'service.get_all_notifications_for_service',
        service_id=sample_service.id
    )

    assert resp['notifications'][0]['id'] == str(normal_noti.id)
    assert resp['notifications'][0]['template']['redact_personalisation'] is False

    assert resp['notifications'][1]['id'] == str(redacted_noti.id)
    assert resp['notifications'][1]['template']['redact_personalisation'] is True


def test_search_for_notification_by_to_field_returns_personlisation(
    client,
    notify_db,
    notify_db_session,
    sample_template_with_placeholders
):
    create_sample_notification(
        notify_db,
        notify_db_session,
        to_field='+447700900855',
        normalised_to='447700900855',
        template=sample_template_with_placeholders,
        personalisation={"name": "Foo"}
    )

    response = client.get(
        '/service/{}/notifications?to={}'.format(
            sample_template_with_placeholders.service_id, '+447700900855'
        ),
        headers=[create_authorization_header()]
    )
    notifications = json.loads(response.get_data(as_text=True))['notifications']

    assert response.status_code == 200
    assert len(notifications) == 1
    assert 'personalisation' in notifications[0].keys()
    assert notifications[0]['personalisation']['name'] == 'Foo'


def test_is_service_name_unique_returns_200_if_unique(client):
    response = client.get('/service/unique?name=something&email_from=something',
                          headers=[create_authorization_header()])
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {"result": True}


@pytest.mark.parametrize('name, email_from',
                         [("something unique", "something"),
                          ("unique", "something.unique"),
                          ("something unique", "something.unique")
                          ])
def test_is_service_name_unique_returns_200_and_false(client, notify_db, notify_db_session, name, email_from):
    create_service(service_name='something unique', email_from='something.unique')
    response = client.get('/service/unique?name={}&email_from={}'.format(name, email_from),
                          headers=[create_authorization_header()])
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == {"result": False}


def test_is_service_name_unique_returns_400_when_name_does_not_exist(client):
    response = client.get('/service/unique', headers=[create_authorization_header()])
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp["message"][0]["name"] == ["Can't be empty"]
    assert json_resp["message"][1]["email_from"] == ["Can't be empty"]


def test_get_email_reply_to_addresses_when_there_are_no_reply_to_email_addresses(client, sample_service):
    response = client.get('/service/{}/email-reply-to'.format(sample_service.id),
                          headers=[create_authorization_header()])

    assert json.loads(response.get_data(as_text=True)) == []
    assert response.status_code == 200


def test_get_email_reply_to_addresses_with_one_email_address(client, notify_db, notify_db_session):
    service = create_service()
    create_reply_to_email(service, 'test@mail.com')

    response = client.get('/service/{}/email-reply-to'.format(service.id),
                          headers=[create_authorization_header()])
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 1
    assert json_response[0]['email_address'] == 'test@mail.com'
    assert json_response[0]['is_default']
    assert json_response[0]['created_at']
    assert not json_response[0]['updated_at']
    assert response.status_code == 200


def test_get_email_reply_to_addresses_with_multiple_email_addresses(client, notify_db, notify_db_session):
    service = create_service()
    reply_to_a = create_reply_to_email(service, 'test_a@mail.com')
    reply_to_b = create_reply_to_email(service, 'test_b@mail.com', False)

    response = client.get('/service/{}/email-reply-to'.format(service.id),
                          headers=[create_authorization_header()])
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 2
    assert response.status_code == 200

    assert json_response[0]['id'] == str(reply_to_a.id)
    assert json_response[0]['service_id'] == str(reply_to_a.service_id)
    assert json_response[0]['email_address'] == 'test_a@mail.com'
    assert json_response[0]['is_default']
    assert json_response[0]['created_at']
    assert not json_response[0]['updated_at']

    assert json_response[1]['id'] == str(reply_to_b.id)
    assert json_response[1]['service_id'] == str(reply_to_b.service_id)
    assert json_response[1]['email_address'] == 'test_b@mail.com'
    assert not json_response[1]['is_default']
    assert json_response[1]['created_at']
    assert not json_response[1]['updated_at']


def test_add_service_reply_to_email_address(client, sample_service):
    data = json.dumps({"email_address": "new@reply.com", "is_default": True})
    response = client.post('/service/{}/email-reply-to'.format(sample_service.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 1
    assert json_resp['data'] == results[0].serialize()


def test_add_service_reply_to_email_address_can_add_multiple_addresses(client, sample_service):
    data = json.dumps({"email_address": "first@reply.com", "is_default": True})
    client.post('/service/{}/email-reply-to'.format(sample_service.id),
                data=data,
                headers=[('Content-Type', 'application/json'), create_authorization_header()])

    second = json.dumps({"email_address": "second@reply.com", "is_default": True})
    response = client.post('/service/{}/email-reply-to'.format(sample_service.id),
                           data=second,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 2
    default = [x for x in results if x.is_default]
    assert json_resp['data'] == default[0].serialize()
    first_reply_to_not_default = [x for x in results if not x.is_default]
    assert first_reply_to_not_default[0].email_address == 'first@reply.com'


def test_add_service_reply_to_email_address_raise_exception_if_no_default(client, sample_service):
    data = json.dumps({"email_address": "first@reply.com", "is_default": False})
    response = client.post('/service/{}/email-reply-to'.format(sample_service.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == 'You must have at least one reply to email address as the default.'


def test_add_service_reply_to_email_address_404s_when_invalid_service_id(client, notify_db, notify_db_session):
    response = client.post('/service/{}/email-reply-to'.format(uuid.uuid4()),
                           data={},
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result['result'] == 'error'
    assert result['message'] == 'No result found'


def test_update_service_reply_to_email_address(client, sample_service):
    original_reply_to = create_reply_to_email(service=sample_service, email_address="some@email.com")
    data = json.dumps({"email_address": "changed@reply.com", "is_default": True})
    response = client.post('/service/{}/email-reply-to/{}'.format(sample_service.id, original_reply_to.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceEmailReplyTo.query.all()
    assert len(results) == 1
    assert json_resp['data'] == results[0].serialize()


def test_update_service_reply_to_email_address_returns_400_when_no_default(client, sample_service):
    original_reply_to = create_reply_to_email(service=sample_service, email_address="some@email.com")
    data = json.dumps({"email_address": "changed@reply.com", "is_default": False})
    response = client.post('/service/{}/email-reply-to/{}'.format(sample_service.id, original_reply_to.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == 'You must have at least one reply to email address as the default.'


def test_update_service_reply_to_email_address_404s_when_invalid_service_id(client, notify_db, notify_db_session):
    response = client.post('/service/{}/email-reply-to/{}'.format(uuid.uuid4(), uuid.uuid4()),
                           data={},
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result['result'] == 'error'
    assert result['message'] == 'No result found'


def test_get_email_reply_to_address(client, notify_db, notify_db_session):
    service = create_service()
    reply_to = create_reply_to_email(service, 'test_a@mail.com')

    response = client.get('/service/{}/email-reply-to/{}'.format(service.id, reply_to.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == reply_to.serialize()


def test_get_letter_contacts_when_there_are_no_letter_contacts(client, sample_service):
    response = client.get('/service/{}/letter-contact'.format(sample_service.id),
                          headers=[create_authorization_header()])

    assert json.loads(response.get_data(as_text=True)) == []
    assert response.status_code == 200


def test_get_letter_contacts_with_one_letter_contact(client, notify_db, notify_db_session):
    service = create_service()
    create_letter_contact(service, 'Aberdeen, AB23 1XH')

    response = client.get('/service/{}/letter-contact'.format(service.id),
                          headers=[create_authorization_header()])
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 1
    assert json_response[0]['contact_block'] == 'Aberdeen, AB23 1XH'
    assert json_response[0]['is_default']
    assert json_response[0]['created_at']
    assert not json_response[0]['updated_at']
    assert response.status_code == 200


def test_get_letter_contacts_with_multiple_letter_contacts(client, notify_db, notify_db_session):
    service = create_service()
    letter_contact_a = create_letter_contact(service, 'Aberdeen, AB23 1XH')
    letter_contact_b = create_letter_contact(service, 'London, E1 8QS', False)

    response = client.get('/service/{}/letter-contact'.format(service.id),
                          headers=[create_authorization_header()])
    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response) == 2
    assert response.status_code == 200

    assert json_response[0]['id'] == str(letter_contact_a.id)
    assert json_response[0]['service_id'] == str(letter_contact_a.service_id)
    assert json_response[0]['contact_block'] == 'Aberdeen, AB23 1XH'
    assert json_response[0]['is_default']
    assert json_response[0]['created_at']
    assert not json_response[0]['updated_at']

    assert json_response[1]['id'] == str(letter_contact_b.id)
    assert json_response[1]['service_id'] == str(letter_contact_b.service_id)
    assert json_response[1]['contact_block'] == 'London, E1 8QS'
    assert not json_response[1]['is_default']
    assert json_response[1]['created_at']
    assert not json_response[1]['updated_at']


def test_get_letter_contact_by_id(client, notify_db, notify_db_session):
    service = create_service()
    letter_contact = create_letter_contact(service, 'London, E1 8QS')

    response = client.get('/service/{}/letter-contact/{}'.format(service.id, letter_contact.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == letter_contact.serialize()


def test_get_letter_contact_return_404_when_invalid_contact_id(client, notify_db, notify_db_session):
    service = create_service()

    response = client.get('/service/{}/letter-contact/{}'.format(service.id, '93d59f88-4aa1-453c-9900-f61e2fc8a2de'),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 404


def test_add_service_contact_block(client, sample_service):
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": True})
    response = client.post('/service/{}/letter-contact'.format(sample_service.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceLetterContact.query.all()
    assert len(results) == 1
    assert json_resp['data'] == results[0].serialize()


def test_add_service_letter_contact_can_add_multiple_addresses(client, sample_service):
    first = json.dumps({"contact_block": "London, E1 8QS", "is_default": True})
    client.post('/service/{}/letter-contact'.format(sample_service.id),
                data=first,
                headers=[('Content-Type', 'application/json'), create_authorization_header()])

    second = json.dumps({"contact_block": "Aberdeen, AB23 1XH", "is_default": True})
    response = client.post('/service/{}/letter-contact'.format(sample_service.id),
                           data=second,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceLetterContact.query.all()
    assert len(results) == 2
    default = [x for x in results if x.is_default]
    assert json_resp['data'] == default[0].serialize()
    first_letter_contact_not_default = [x for x in results if not x.is_default]
    assert first_letter_contact_not_default[0].contact_block == 'London, E1 8QS'


def test_add_service_letter_contact_block_raise_exception_if_no_default(client, sample_service):
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": False})
    response = client.post('/service/{}/letter-contact'.format(sample_service.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == 'You must have at least one letter contact as the default.'


def test_add_service_letter_contact_block_404s_when_invalid_service_id(client, notify_db, notify_db_session):
    response = client.post('/service/{}/letter-contact'.format(uuid.uuid4()),
                           data={},
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result['result'] == 'error'
    assert result['message'] == 'No result found'


def test_update_service_letter_contact(client, sample_service):
    original_letter_contact = create_letter_contact(service=sample_service, contact_block="Aberdeen, AB23 1XH")
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": True})
    response = client.post('/service/{}/letter-contact/{}'.format(sample_service.id, original_letter_contact.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    results = ServiceLetterContact.query.all()
    assert len(results) == 1
    assert json_resp['data'] == results[0].serialize()


def test_update_service_letter_contact_returns_400_when_no_default(client, sample_service):
    original_reply_to = create_letter_contact(service=sample_service, contact_block="Aberdeen, AB23 1XH")
    data = json.dumps({"contact_block": "London, E1 8QS", "is_default": False})
    response = client.post('/service/{}/letter-contact/{}'.format(sample_service.id, original_reply_to.id),
                           data=data,
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['message'] == 'You must have at least one letter contact as the default.'


def test_update_service_letter_contact_returns_404_when_invalid_service_id(client, notify_db, notify_db_session):
    response = client.post('/service/{}/letter-contact/{}'.format(uuid.uuid4(), uuid.uuid4()),
                           data={},
                           headers=[('Content-Type', 'application/json'), create_authorization_header()])

    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result['result'] == 'error'
    assert result['message'] == 'No result found'


def test_add_service_sms_sender_can_add_multiple_senders(client, notify_db_session):
    service = create_service()
    data = {
        "sms_sender": 'second',
        "is_default": False,
    }
    response = client.post('/service/{}/sms-sender'.format(service.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['sms_sender'] == 'second'
    assert not resp_json['is_default']
    senders = ServiceSmsSender.query.all()
    assert len(senders) == 2


def test_add_service_sms_sender_when_it_is_an_inbound_number_updates_the_only_existing_sms_sender(
        client, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value='GOVUK')
    inbound_number = create_inbound_number(number='12345')
    data = {
        "sms_sender": str(inbound_number.id),
        "is_default": True,
        "inbound_number_id": str(inbound_number.id)
    }
    response = client.post('/service/{}/sms-sender'.format(service.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 201
    updated_number = InboundNumber.query.get(inbound_number.id)
    assert updated_number.service_id == service.id
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['sms_sender'] == inbound_number.number
    assert resp_json['inbound_number_id'] == str(inbound_number.id)
    assert resp_json['is_default']

    senders = ServiceSmsSender.query.all()
    assert len(senders) == 1


def test_add_service_sms_sender_when_it_is_an_inbound_number_inserts_new_sms_sender_when_more_than_one(
        client, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value='GOVUK')
    create_service_sms_sender(service=service, sms_sender="second", is_default=False)
    inbound_number = create_inbound_number(number='12345')
    data = {
        "sms_sender": str(inbound_number.id),
        "is_default": True,
        "inbound_number_id": str(inbound_number.id)
    }
    response = client.post('/service/{}/sms-sender'.format(service.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 201
    updated_number = InboundNumber.query.get(inbound_number.id)
    assert updated_number.service_id == service.id
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['sms_sender'] == inbound_number.number
    assert resp_json['inbound_number_id'] == str(inbound_number.id)
    assert resp_json['is_default']

    senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(senders) == 3


def test_add_service_sms_sender_switches_default(client, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value='first')
    data = {
        "sms_sender": 'second',
        "is_default": True,
    }
    response = client.post('/service/{}/sms-sender'.format(service.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 201
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['sms_sender'] == 'second'
    assert not resp_json['inbound_number_id']
    assert resp_json['is_default']
    sms_senders = ServiceSmsSender.query.filter_by(sms_sender='first').first()
    assert not sms_senders.is_default


def test_add_service_sms_sender_return_404_when_service_does_not_exist(client):
    data = {
        "sms_sender": '12345',
        "is_default": False
    }
    response = client.post('/service/{}/sms-sender'.format(uuid.uuid4()),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result['result'] == 'error'
    assert result['message'] == 'No result found'


def test_update_service_sms_sender(client, notify_db_session):
    service = create_service()
    service_sms_sender = create_service_sms_sender(service=service, sms_sender='1235', is_default=False)
    data = {
        "sms_sender": 'second',
        "is_default": False,
    }
    response = client.post('/service/{}/sms-sender/{}'.format(service.id, service_sms_sender.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['sms_sender'] == 'second'
    assert not resp_json['inbound_number_id']
    assert not resp_json['is_default']


def test_update_service_sms_sender_switches_default(client, notify_db_session):
    service = create_service_with_defined_sms_sender(sms_sender_value='first')
    service_sms_sender = create_service_sms_sender(service=service, sms_sender='1235', is_default=False)
    data = {
        "sms_sender": 'second',
        "is_default": True,
    }
    response = client.post('/service/{}/sms-sender/{}'.format(service.id, service_sms_sender.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json['sms_sender'] == 'second'
    assert not resp_json['inbound_number_id']
    assert resp_json['is_default']
    sms_senders = ServiceSmsSender.query.filter_by(sms_sender='first').first()
    assert not sms_senders.is_default


def test_update_service_sms_sender_does_not_allow_sender_update_for_inbound_number(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number('12345', service_id=service.id)
    service_sms_sender = create_service_sms_sender(service=service,
                                                   sms_sender='1235',
                                                   is_default=False,
                                                   inbound_number_id=inbound_number.id)
    data = {
        "sms_sender": 'second',
        "is_default": True,
        "inbound_number_id": str(inbound_number.id)
    }
    response = client.post('/service/{}/sms-sender/{}'.format(service.id, service_sms_sender.id),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 400


def test_update_service_sms_sender_return_404_when_service_does_not_exist(client):
    data = {
        "sms_sender": '12345',
        "is_default": False
    }
    response = client.post('/service/{}/sms-sender/{}'.format(uuid.uuid4(), uuid.uuid4()),
                           data=json.dumps(data),
                           headers=[('Content-Type', 'application/json'), create_authorization_header()]
                           )
    assert response.status_code == 404
    result = json.loads(response.get_data(as_text=True))
    assert result['result'] == 'error'
    assert result['message'] == 'No result found'


def test_get_service_sms_sender_by_id(client, notify_db_session):
    service_sms_sender = create_service_sms_sender(service=create_service(),
                                                   sms_sender='1235',
                                                   is_default=False)
    response = client.get('/service/{}/sms-sender/{}'.format(service_sms_sender.service_id, service_sms_sender.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == service_sms_sender.serialize()


def test_get_service_sms_sender_by_id_returns_404_when_service_does_not_exist(client, notify_db_session):
    service_sms_sender = create_service_sms_sender(service=create_service(),
                                                   sms_sender='1235',
                                                   is_default=False)
    response = client.get('/service/{}/sms-sender/{}'.format(uuid.uuid4(), service_sms_sender.id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 404


def test_get_service_sms_sender_by_id_returns_404_when_sms_sender_does_not_exist(client, notify_db_session):
    service = create_service()
    response = client.get('/service/{}/sms-sender/{}'.format(service.id, uuid.uuid4()),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 404


def test_get_service_sms_senders_for_service(client, notify_db_session):
    service_sms_sender = create_service_sms_sender(service=create_service(),
                                                   sms_sender='second',
                                                   is_default=False)
    response = client.get('/service/{}/sms-sender'.format(service_sms_sender.service_id),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp) == 2
    assert json_resp[0]['is_default']
    assert json_resp[0]['sms_sender'] == current_app.config['FROM_NUMBER']
    assert not json_resp[1]['is_default']
    assert json_resp[1]['sms_sender'] == 'second'


def test_get_service_sms_senders_for_service_returns_empty_list_when_service_does_not_exist(client):
    response = client.get('/service/{}/sms-sender'.format(uuid.uuid4()),
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True)) == []


def test_get_platform_stats(client, notify_db_session):
    service_1 = create_service(service_name='Service 1')
    service_2 = create_service(service_name='Service 2')
    sms_template = create_template(service=service_1)
    email_template = create_template(service=service_2, template_type=EMAIL_TYPE)
    letter_template = create_template(service=service_2, template_type=LETTER_TYPE)
    create_notification(template=sms_template, status='sending')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=email_template, status='temporary-failure')
    create_notification(template=email_template, status='delivered')
    create_notification(template=letter_template, status='sending')
    create_notification(template=letter_template, status='sending')

    response = client.get('/service/platform-stats',
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['email'] == {'delivered': 1, 'requested': 2, 'failed': 1}
    assert json_resp['letter'] == {'delivered': 0, 'requested': 2, 'failed': 0}
    assert json_resp['sms'] == {'delivered': 3, 'requested': 4, 'failed': 0}


def test_get_platform_stats_creates_zero_stats(client, notify_db_session):
    service_1 = create_service(service_name='Service 1')
    service_2 = create_service(service_name='Service 2')
    sms_template = create_template(service=service_1)
    email_template = create_template(service=service_2, template_type=EMAIL_TYPE)
    create_notification(template=sms_template, status='sending')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=sms_template, status='delivered')
    create_notification(template=email_template, status='temporary-failure')
    create_notification(template=email_template, status='delivered')

    response = client.get('/service/platform-stats',
                          headers=[('Content-Type', 'application/json'), create_authorization_header()]
                          )
    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['email'] == {'failed': 1, 'requested': 2, 'delivered': 1}
    assert json_resp['letter'] == {'failed': 0, 'requested': 0, 'delivered': 0}
    assert json_resp['sms'] == {'failed': 0, 'requested': 4, 'delivered': 3}
