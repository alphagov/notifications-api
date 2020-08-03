import json
import uuid
from datetime import datetime, timedelta

import pytest
import pytz
import requests_mock
from flask import current_app, url_for
from sqlalchemy.orm.session import make_transient

from app import db
from app.clients.sms.firetext import FiretextClient
from app.dao.api_key_dao import save_model_api_key
from app.dao.invited_user_dao import save_invited_user
from app.dao.jobs_dao import dao_create_job
from app.dao.notifications_dao import dao_create_notification
from app.dao.organisation_dao import dao_create_organisation
from app.dao.services_dao import (dao_create_service, dao_add_user_to_service)
from app.dao.templates_dao import dao_create_template
from app.dao.users_dao import create_secret_code, create_user_code
from app.history_meta import create_history
from app.models import (
    Service,
    Template,
    TemplateHistory,
    ApiKey,
    Job,
    Organisation,
    Notification,
    NotificationHistory,
    InvitedUser,
    Permission,
    ProviderDetails,
    ProviderDetailsHistory,
    ProviderRates,
    ServiceGuestList,
    KEY_TYPE_NORMAL,
    KEY_TYPE_TEST,
    KEY_TYPE_TEAM,
    EMAIL_TYPE,
    SMS_TYPE,
    LETTER_TYPE,
    SERVICE_PERMISSION_TYPES,
    ServiceEmailReplyTo
)
from tests import create_authorization_header
from tests.app.db import (
    create_user,
    create_template,
    create_notification,
    create_service,
    create_api_key,
    create_inbound_number,
    create_letter_contact,
    create_invited_org_user,
    create_job
)


@pytest.yield_fixture
def rmock():
    with requests_mock.mock() as rmock:
        yield rmock


@pytest.fixture(scope='function')
def service_factory(notify_db, notify_db_session):
    class ServiceFactory(object):
        def get(self, service_name, user=None, template_type=None, email_from=None):
            if not user:
                user = create_user()
            if not email_from:
                email_from = service_name

            service = create_service(
                email_from=email_from,
                service_name=service_name,
                service_permissions=None,
                user=user,
                check_if_service_exists=True,
            )
            if template_type == 'email':
                create_template(
                    service,
                    template_name="Template Name",
                    template_type=template_type,
                    subject=service.email_from,
                )
            else:
                create_template(
                    service,
                    template_name="Template Name",
                    template_type='sms',
                )
            return service

    return ServiceFactory()


@pytest.fixture(scope='function')
def sample_user(notify_db_session):
    return create_user()


@pytest.fixture(scope='function')
def notify_user(notify_db_session):
    return create_user(
        email="notify-service-user@digital.cabinet-office.gov.uk",
        id_=current_app.config['NOTIFY_USER_ID']
    )


def create_code(notify_db_session, code_type):
    code = create_secret_code()
    usr = create_user()
    return create_user_code(usr, code, code_type), code


@pytest.fixture(scope='function')
def sample_sms_code(notify_db_session):
    code, txt_code = create_code(notify_db_session, code_type="sms")
    code.txt_code = txt_code
    return code


@pytest.fixture(scope='function')
def sample_service(notify_db_session):
    user = create_user()
    service_name = 'Sample service'
    email_from = service_name.lower().replace(' ', '.')

    data = {
        'name': service_name,
        'message_limit': 1000,
        'restricted': False,
        'email_from': email_from,
        'created_by': user,
        'crown': True
    }
    service = Service.query.filter_by(name=service_name).first()
    if not service:
        service = Service(**data)
        dao_create_service(service, user, service_permissions=None)
    else:
        if user not in service.users:
            dao_add_user_to_service(service, user)

    return service


@pytest.fixture(scope='function', name='sample_service_full_permissions')
def _sample_service_full_permissions(notify_db_session):
    service = create_service(
        service_name="sample service full permissions",
        service_permissions=set(SERVICE_PERMISSION_TYPES),
        check_if_service_exists=True
    )
    create_inbound_number('12345', service_id=service.id)
    return service


@pytest.fixture(scope='function', name='sample_service_custom_letter_contact_block')
def _sample_service_custom_letter_contact_block(sample_service):
    create_letter_contact(sample_service, contact_block='((contact block))')
    return sample_service


@pytest.fixture(scope='function')
def sample_template(notify_db_session):
    user = create_user()
    service = create_service(service_permissions=[EMAIL_TYPE, SMS_TYPE], check_if_service_exists=True)

    data = {
        'name': 'Template Name',
        'template_type': 'sms',
        'content': 'This is a template:\nwith a newline',
        'service': service,
        'created_by': user,
        'archived': False,
        'hidden': False,
        'process_type': 'normal'
    }
    template = Template(**data)
    dao_create_template(template)

    return template


@pytest.fixture(scope='function')
def sample_template_without_sms_permission(notify_db_session):
    service = create_service(service_permissions=[EMAIL_TYPE], check_if_service_exists=True)
    return create_template(service, template_type=SMS_TYPE)


@pytest.fixture(scope='function')
def sample_template_with_placeholders(sample_service):
    # deliberate space and title case in placeholder
    return create_template(sample_service, content="Hello (( Name))\nYour thing is due soon")


@pytest.fixture(scope='function')
def sample_sms_template_with_html(sample_service):
    # deliberate space and title case in placeholder
    return create_template(sample_service, content="Hello (( Name))\nHere is <em>some HTML</em> & entities")


@pytest.fixture(scope='function')
def sample_email_template(notify_db_session):
    user = create_user()
    service = create_service(user=user, service_permissions=[EMAIL_TYPE, SMS_TYPE], check_if_service_exists=True)
    data = {
        'name': 'Email Template Name',
        'template_type': EMAIL_TYPE,
        'content': 'This is a template',
        'service': service,
        'created_by': user,
        'subject': 'Email Subject'
    }
    template = Template(**data)
    dao_create_template(template)
    return template


@pytest.fixture(scope='function')
def sample_template_without_email_permission(notify_db_session):
    service = create_service(service_permissions=[SMS_TYPE], check_if_service_exists=True)
    return create_template(service, template_type=EMAIL_TYPE)


@pytest.fixture
def sample_letter_template(sample_service_full_permissions):
    return create_template(sample_service_full_permissions, template_type=LETTER_TYPE, postage='second')


@pytest.fixture
def sample_trial_letter_template(sample_service_full_permissions):
    sample_service_full_permissions.restricted = True
    return create_template(sample_service_full_permissions, template_type=LETTER_TYPE)


@pytest.fixture(scope='function')
def sample_email_template_with_placeholders(sample_service):
    return create_template(
        sample_service,
        template_type=EMAIL_TYPE,
        subject="((name))",
        content="Hello ((name))\nThis is an email from GOV.UK",
    )


@pytest.fixture(scope='function')
def sample_email_template_with_html(sample_service):
    return create_template(
        sample_service,
        template_type=EMAIL_TYPE,
        subject="((name)) <em>some HTML</em>",
        content="Hello ((name))\nThis is an email from GOV.UK with <em>some HTML</em>",
    )


@pytest.fixture(scope='function')
def sample_api_key(notify_db_session):
    service = create_service(check_if_service_exists=True)
    data = {'service': service, 'name': uuid.uuid4(), 'created_by': service.created_by, 'key_type': KEY_TYPE_NORMAL}
    api_key = ApiKey(**data)
    save_model_api_key(api_key)
    return api_key


@pytest.fixture(scope='function')
def sample_test_api_key(sample_api_key):
    service = create_service(check_if_service_exists=True)

    return create_api_key(
        service,
        key_type=KEY_TYPE_TEST
    )


@pytest.fixture(scope='function')
def sample_team_api_key(sample_api_key):
    service = create_service(check_if_service_exists=True)

    return create_api_key(
        service,
        key_type=KEY_TYPE_TEAM
    )


@pytest.fixture(scope='function')
def sample_job(notify_db_session):
    service = create_service(check_if_service_exists=True)
    template = create_template(service=service)
    data = {
        'id': uuid.uuid4(),
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'original_file_name': 'some.csv',
        'notification_count': 1,
        'created_at': datetime.utcnow(),
        'created_by': service.created_by,
        'job_status': 'pending',
        'scheduled_for': None,
        'processing_started': None,
        'archived': False
    }
    job = Job(**data)
    dao_create_job(job)
    return job


@pytest.fixture(scope='function')
def sample_job_with_placeholdered_template(
        sample_job,
        sample_template_with_placeholders,
):
    sample_job.template = sample_template_with_placeholders

    return sample_job


@pytest.fixture(scope='function')
def sample_scheduled_job(sample_template_with_placeholders):
    return create_job(
        sample_template_with_placeholders,
        job_status='scheduled',
        scheduled_for=(datetime.utcnow() + timedelta(minutes=60)).isoformat()
    )


@pytest.fixture
def sample_letter_job(sample_letter_template):
    service = sample_letter_template.service
    data = {
        'id': uuid.uuid4(),
        'service_id': service.id,
        'service': service,
        'template_id': sample_letter_template.id,
        'template_version': sample_letter_template.version,
        'original_file_name': 'some.csv',
        'notification_count': 1,
        'created_at': datetime.utcnow(),
        'created_by': service.created_by,
    }
    job = Job(**data)
    dao_create_job(job)
    return job


@pytest.fixture(scope='function')
def sample_notification_with_job(notify_db_session):
    service = create_service(check_if_service_exists=True)
    template = create_template(service=service)
    job = create_job(template=template)
    return create_notification(
        template=template,
        job=job,
        job_row_number=None,
        to_field=None,
        status='created',
        reference=None,
        created_at=None,
        sent_at=None,
        billable_units=1,
        personalisation=None,
        api_key=None,
        key_type=KEY_TYPE_NORMAL
    )


@pytest.fixture(scope='function')
def sample_notification(notify_db_session):
    created_at = datetime.utcnow()
    service = create_service(check_if_service_exists=True)
    template = create_template(service=service)

    api_key = ApiKey.query.filter(ApiKey.service == template.service, ApiKey.key_type == KEY_TYPE_NORMAL).first()
    if not api_key:
        api_key = create_api_key(template.service, key_type=KEY_TYPE_NORMAL)

    notification_id = uuid.uuid4()
    to = '+447700900855'

    data = {
        'id': notification_id,
        'to': to,
        'job_id': None,
        'job': None,
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'status': 'created',
        'reference': None,
        'created_at': created_at,
        'sent_at': None,
        'billable_units': 1,
        'personalisation': None,
        'notification_type': template.template_type,
        'api_key': api_key,
        'api_key_id': api_key and api_key.id,
        'key_type': api_key.key_type,
        'sent_by': None,
        'updated_at': None,
        'client_reference': None,
        'rate_multiplier': 1.0,
        'normalised_to': None,
        'postage': None,
    }

    notification = Notification(**data)
    dao_create_notification(notification)

    return notification


@pytest.fixture
def sample_letter_notification(sample_letter_template):
    address = {
        'address_line_1': 'A1',
        'address_line_2': 'A2',
        'address_line_3': 'A3',
        'address_line_4': 'A4',
        'address_line_5': 'A5',
        'address_line_6': 'A6',
        'postcode': 'A_POST'
    }
    return create_notification(sample_letter_template, reference='foo', personalisation=address)


@pytest.fixture(scope='function')
def sample_email_notification(notify_db_session):
    created_at = datetime.utcnow()
    service = create_service(check_if_service_exists=True)
    template = create_template(service, template_type=EMAIL_TYPE)
    job = create_job(template)

    notification_id = uuid.uuid4()

    to = 'foo@bar.com'

    data = {
        'id': notification_id,
        'to': to,
        'job_id': job.id,
        'job': job,
        'service_id': service.id,
        'service': service,
        'template_id': template.id,
        'template_version': template.version,
        'status': 'created',
        'reference': None,
        'created_at': created_at,
        'billable_units': 0,
        'personalisation': None,
        'notification_type': template.template_type,
        'api_key_id': None,
        'key_type': KEY_TYPE_NORMAL,
        'job_row_number': 1
    }
    notification = Notification(**data)
    dao_create_notification(notification)
    return notification


@pytest.fixture(scope='function')
def sample_notification_history(notify_db, notify_db_session, sample_template):
    created_at = datetime.utcnow()
    sent_at = datetime.utcnow()
    notification_type = sample_template.template_type
    api_key = create_api_key(sample_template.service, key_type=KEY_TYPE_NORMAL)

    notification_history = NotificationHistory(
        id=uuid.uuid4(),
        service=sample_template.service,
        template_id=sample_template.id,
        template_version=sample_template.version,
        status='created',
        created_at=created_at,
        notification_type=notification_type,
        key_type=KEY_TYPE_NORMAL,
        api_key=api_key,
        api_key_id=api_key and api_key.id,
        sent_at=sent_at
    )
    notify_db.session.add(notification_history)
    notify_db.session.commit()

    return notification_history


@pytest.fixture(scope='function')
def sample_invited_user(notify_db_session):
    service = create_service(check_if_service_exists=True)
    to_email_address = 'invited_user@digital.gov.uk'

    from_user = service.users[0]

    data = {
        'service': service,
        'email_address': to_email_address,
        'from_user': from_user,
        'permissions': 'send_messages,manage_service,manage_api_keys',
        'folder_permissions': ['folder_1_id', 'folder_2_id'],
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)
    return invited_user


@pytest.fixture(scope='function')
def sample_invited_org_user(sample_user, sample_organisation):
    return create_invited_org_user(sample_organisation, sample_user)


@pytest.fixture(scope='function')
def sample_user_service_permission(notify_db_session):
    user = create_user()
    service = create_service(user=user, check_if_service_exists=True)
    permission = 'manage_settings'

    data = {
        'user': user,
        'service': service,
        'permission': permission
    }
    p_model = Permission.query.filter_by(
        user=user,
        service=service,
        permission=permission).first()
    if not p_model:
        p_model = Permission(**data)
        db.session.add(p_model)
        db.session.commit()
    return p_model


@pytest.fixture(scope='function')
def fake_uuid():
    return "6ce466d0-fd6a-11e5-82f5-e0accb9d11a6"


@pytest.fixture(scope='function')
def ses_provider():
    return ProviderDetails.query.filter_by(identifier='ses').one()


@pytest.fixture(scope='function')
def mmg_provider():
    return ProviderDetails.query.filter_by(identifier='mmg').one()


@pytest.fixture(scope='function')
def mock_firetext_client(mocker):
    client = FiretextClient()
    statsd_client = mocker.Mock()
    current_app = mocker.Mock(config={
        'FIRETEXT_URL': 'https://example.com/firetext',
        'FIRETEXT_API_KEY': 'foo',
        'FROM_NUMBER': 'bar'
    })
    client.init_app(current_app, statsd_client)
    return client


@pytest.fixture(scope='function')
def sms_code_template(notify_db,
                      notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='SMS_CODE_TEMPLATE_ID',
        content='((verify_code))',
        template_type='sms'
    )


@pytest.fixture(scope='function')
def email_2fa_code_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='EMAIL_2FA_TEMPLATE_ID',
        content=(
            'Hi ((name)),'
            ''
            'To sign in to GOV.​UK Notify please open this link:'
            '((url))'
        ),
        subject='Sign in to GOV.UK Notify',
        template_type='email'
    )


@pytest.fixture(scope='function')
def email_verification_template(notify_db,
                                notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID',
        content='((user_name)) use ((url)) to complete registration',
        template_type='email'
    )


@pytest.fixture(scope='function')
def invitation_email_template(notify_db,
                              notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    content = '((user_name)) is invited to Notify by ((service_name)) ((url)) to complete registration',
    return create_custom_template(
        service=service,
        user=user,
        template_config_name='INVITATION_EMAIL_TEMPLATE_ID',
        content=content,
        subject='Invitation to ((service_name))',
        template_type='email'
    )


@pytest.fixture(scope='function')
def org_invite_email_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID',
        content='((user_name)) ((organisation_name)) ((url))',
        subject='Invitation to ((organisation_name))',
        template_type='email'
    )


@pytest.fixture(scope='function')
def password_reset_email_template(notify_db,
                                  notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='PASSWORD_RESET_TEMPLATE_ID',
        content='((user_name)) you can reset password by clicking ((url))',
        subject='Reset your password',
        template_type='email'
    )


@pytest.fixture(scope='function')
def verify_reply_to_address_email_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='REPLY_TO_EMAIL_ADDRESS_VERIFICATION_TEMPLATE_ID',
        content="Hi,This address has been provided as the reply-to email address so we are verifying if it's working",
        subject='Your GOV.UK Notify reply-to email address',
        template_type='email'
    )


@pytest.fixture(scope='function')
def team_member_email_edit_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID',
        content='Hi ((name)) ((servicemanagername)) changed your email to ((email address))',
        subject='Your GOV.UK Notify email address has changed',
        template_type='email'
    )


@pytest.fixture(scope='function')
def team_member_mobile_edit_template(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    return create_custom_template(
        service=service,
        user=user,
        template_config_name='TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID',
        content='Your mobile number was changed by ((servicemanagername)).',
        template_type='sms'
    )


@pytest.fixture(scope='function')
def already_registered_template(notify_db,
                                notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)

    content = """Sign in here: ((signin_url)) If you’ve forgotten your password,
                          you can reset it here: ((forgot_password_url)) feedback:((feedback_url))"""
    return create_custom_template(
        service=service, user=user,
        template_config_name='ALREADY_REGISTERED_EMAIL_TEMPLATE_ID',
        content=content,
        template_type='email'
    )


@pytest.fixture(scope='function')
def change_email_confirmation_template(notify_db,
                                       notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    content = """Hi ((name)),
              Click this link to confirm your new email address:
              ((url))
              If you didn’t try to change the email address for your GOV.UK Notify account, let us know here:
              ((feedback_url))"""
    template = create_custom_template(
        service=service,
        user=user,
        template_config_name='CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID',
        content=content,
        template_type='email'
    )
    return template


@pytest.fixture(scope='function')
def mou_signed_templates(notify_db, notify_db_session):
    service, user = notify_service(notify_db, notify_db_session)
    import importlib
    alembic_script = importlib.import_module('migrations.versions.0298_add_mou_signed_receipt')

    return {
        config_name: create_custom_template(
            service,
            user,
            config_name,
            'email',
            content='\n'.join(
                next(
                    x
                    for x in alembic_script.templates
                    if x['id'] == current_app.config[config_name]
                )['content_lines']
            ),
        )
        for config_name in [
            'MOU_SIGNER_RECEIPT_TEMPLATE_ID',
            'MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID',
            'MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID',
            'MOU_NOTIFY_TEAM_ALERT_TEMPLATE_ID',
        ]
    }


def create_custom_template(service, user, template_config_name, template_type, content='', subject=None):
    template = Template.query.get(current_app.config[template_config_name])
    if not template:
        data = {
            'id': current_app.config[template_config_name],
            'name': template_config_name,
            'template_type': template_type,
            'content': content,
            'service': service,
            'created_by': user,
            'subject': subject,
            'archived': False
        }
        template = Template(**data)
        db.session.add(template)
        db.session.add(create_history(template, TemplateHistory))
        db.session.commit()
    return template


def notify_service(notify_db, notify_db_session):
    user = create_user()
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])
    if not service:
        service = Service(
            name='Notify Service',
            message_limit=1000,
            restricted=False,
            email_from='notify.service',
            created_by=user,
            prefix_sms=False,
        )
        dao_create_service(
            service=service,
            service_id=current_app.config['NOTIFY_SERVICE_ID'],
            user=user
        )

        data = {
            'service': service,
            'email_address': "notify@gov.uk",
            'is_default': True,
        }
        reply_to = ServiceEmailReplyTo(**data)

        db.session.add(reply_to)
        db.session.commit()

    return service, user


@pytest.fixture(scope='function')
def sample_service_guest_list(notify_db, notify_db_session):
    service = create_service(check_if_service_exists=True)
    guest_list_user = ServiceGuestList.from_string(service.id, EMAIL_TYPE, 'guest_list_user@digital.gov.uk')

    notify_db.session.add(guest_list_user)
    notify_db.session.commit()
    return guest_list_user


@pytest.fixture
def sample_inbound_numbers(sample_service):
    service = create_service(service_name='sample service 2', check_if_service_exists=True)
    inbound_numbers = list()
    inbound_numbers.append(create_inbound_number(number='1', provider='mmg'))
    inbound_numbers.append(create_inbound_number(number='2', provider='mmg', active=False, service_id=service.id))
    inbound_numbers.append(create_inbound_number(number='3', provider='firetext', service_id=sample_service.id))
    return inbound_numbers


@pytest.fixture
def sample_organisation(notify_db_session):
    org = Organisation(name='sample organisation')
    dao_create_organisation(org)
    return org


@pytest.fixture
def restore_provider_details(notify_db, notify_db_session):
    """
    We view ProviderDetails as a static in notify_db_session, since we don't modify it... except we do, we updated
    priority. This fixture is designed to be used in tests that will knowingly touch provider details, to restore them
    to previous state.

    Note: This doesn't technically require notify_db_session (only notify_db), but kept as a requirement to encourage
    good usage - if you're modifying ProviderDetails' state then it's good to clear down the rest of the DB too
    """
    existing_provider_details = ProviderDetails.query.all()
    existing_provider_details_history = ProviderDetailsHistory.query.all()
    # make transient removes the objects from the session - since we'll want to delete them later
    for epd in existing_provider_details:
        make_transient(epd)
    for epdh in existing_provider_details_history:
        make_transient(epdh)

    yield

    # also delete these as they depend on provider_details
    ProviderRates.query.delete()
    ProviderDetails.query.delete()
    ProviderDetailsHistory.query.delete()
    notify_db.session.commit()
    notify_db.session.add_all(existing_provider_details)
    notify_db.session.add_all(existing_provider_details_history)
    notify_db.session.commit()


@pytest.fixture
def admin_request(client):

    class AdminRequest:
        app = client.application

        @staticmethod
        def get(endpoint, _expected_status=200, **endpoint_kwargs):
            resp = client.get(
                url_for(endpoint, **(endpoint_kwargs or {})),
                headers=[create_authorization_header()]
            )
            json_resp = resp.json
            assert resp.status_code == _expected_status
            return json_resp

        @staticmethod
        def post(endpoint, _data=None, _expected_status=200, **endpoint_kwargs):
            resp = client.post(
                url_for(endpoint, **(endpoint_kwargs or {})),
                data=json.dumps(_data),
                headers=[('Content-Type', 'application/json'), create_authorization_header()]
            )
            if resp.get_data():
                json_resp = resp.json
            else:
                json_resp = None
            assert resp.status_code == _expected_status
            return json_resp

        @staticmethod
        def delete(endpoint, _expected_status=204, **endpoint_kwargs):
            resp = client.delete(
                url_for(endpoint, **(endpoint_kwargs or {})),
                headers=[create_authorization_header()]
            )
            if resp.get_data():
                json_resp = resp.json
            else:
                json_resp = None
            assert resp.status_code == _expected_status, json_resp
            return json_resp

    return AdminRequest


def datetime_in_past(days=0, seconds=0):
    return datetime.now(tz=pytz.utc) - timedelta(days=days, seconds=seconds)
