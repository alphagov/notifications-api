import base64
import json
import random
import string
from datetime import datetime, timedelta

import botocore
import pytest
import requests_mock
from PyPDF2.utils import PdfReadError
from freezegun import freeze_time
from notifications_utils import SMS_CHAR_COUNT_LIMIT


from app.models import Template, SMS_TYPE, EMAIL_TYPE, LETTER_TYPE, TemplateHistory
from app.dao.templates_dao import dao_get_template_by_id, dao_redact_template

from tests import create_authorization_header
from tests.app.conftest import (
    sample_template as create_sample_template,
    sample_template_without_email_permission,
    sample_template_without_letter_permission,
    sample_template_without_sms_permission)
from tests.app.db import create_service, create_letter_contact, create_template, create_notification
from tests.conftest import set_config_values


@pytest.mark.parametrize('template_type, subject', [
    (SMS_TYPE, None),
    (EMAIL_TYPE, 'subject'),
    (LETTER_TYPE, 'subject'),
])
def test_should_create_a_new_template_for_a_service(
    client, sample_user, template_type, subject
):
    service = create_service(service_permissions=[template_type])
    data = {
        'name': 'my template',
        'template_type': template_type,
        'content': 'template <b>content</b>',
        'service': str(service.id),
        'created_by': str(sample_user.id)
    }
    if subject:
        data.update({'subject': subject})
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['data']['name'] == 'my template'
    assert json_resp['data']['template_type'] == template_type
    assert json_resp['data']['content'] == 'template <b>content</b>'
    assert json_resp['data']['service'] == str(service.id)
    assert json_resp['data']['id']
    assert json_resp['data']['version'] == 1
    assert json_resp['data']['process_type'] == 'normal'
    assert json_resp['data']['created_by'] == str(sample_user.id)
    if subject:
        assert json_resp['data']['subject'] == 'subject'
    else:
        assert not json_resp['data']['subject']

    template = Template.query.get(json_resp['data']['id'])
    from app.schemas import template_schema
    assert sorted(json_resp['data']) == sorted(template_schema.dump(template).data)


def test_should_raise_error_if_service_does_not_exist_on_create(client, sample_user, fake_uuid):
    data = {
        'name': 'my template',
        'template_type': SMS_TYPE,
        'content': 'template content',
        'service': fake_uuid,
        'created_by': str(sample_user.id)
    }
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(fake_uuid),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'No result found'


@pytest.mark.parametrize('permissions, template_type, subject, expected_error', [
    ([EMAIL_TYPE], SMS_TYPE, None, {'template_type': ['Creating text message templates is not allowed']}),
    ([SMS_TYPE], EMAIL_TYPE, 'subject', {'template_type': ['Creating email templates is not allowed']}),
    ([SMS_TYPE], LETTER_TYPE, 'subject', {'template_type': ['Creating letter templates is not allowed']}),
])
def test_should_raise_error_on_create_if_no_permission(
        client, sample_user, permissions, template_type, subject, expected_error):
    service = create_service(service_permissions=permissions)
    data = {
        'name': 'my template',
        'template_type': template_type,
        'content': 'template content',
        'service': str(service.id),
        'created_by': str(sample_user.id)
    }
    if subject:
        data.update({'subject': subject})

    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 403
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == expected_error


@pytest.mark.parametrize('template_factory, expected_error', [
    (sample_template_without_sms_permission, {'template_type': ['Updating text message templates is not allowed']}),
    (sample_template_without_email_permission, {'template_type': ['Updating email templates is not allowed']}),
    (sample_template_without_letter_permission, {'template_type': ['Updating letter templates is not allowed']})
])
def test_should_be_error_on_update_if_no_permission(
        client, sample_user, template_factory, expected_error, notify_db, notify_db_session):
    template_without_permission = template_factory(notify_db, notify_db_session)
    data = {
        'content': 'new template content',
        'created_by': str(sample_user.id)
    }

    data = json.dumps(data)
    auth_header = create_authorization_header()

    update_response = client.post(
        '/service/{}/template/{}'.format(
            template_without_permission.service_id, template_without_permission.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )

    json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_response.status_code == 403
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == expected_error


def test_should_error_if_created_by_missing(client, sample_user, sample_service):
    service_id = str(sample_service.id)
    data = {
        'name': 'my template',
        'template_type': SMS_TYPE,
        'content': 'template content',
        'service': service_id
    }
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(service_id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'


def test_should_be_error_if_service_does_not_exist_on_update(client, fake_uuid):
    data = {
        'name': 'my template'
    }
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template/{}'.format(fake_uuid, fake_uuid),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 404
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'No result found'


@pytest.mark.parametrize('template_type', [EMAIL_TYPE, LETTER_TYPE])
def test_must_have_a_subject_on_an_email_or_letter_template(client, sample_user, sample_service, template_type):
    data = {
        'name': 'my template',
        'template_type': template_type,
        'content': 'template content',
        'service': str(sample_service.id),
        'created_by': str(sample_user.id)
    }
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    json_resp = json.loads(response.get_data(as_text=True))
    assert response.status_code == 400
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == {'subject': ['Invalid template subject']}


def test_update_should_update_a_template(client, sample_user, sample_template):
    data = {
        'content': 'my template has new content <script type="text/javascript">alert("foo")</script>',
        'created_by': str(sample_user.id)
    }
    data = json.dumps(data)
    auth_header = create_authorization_header()

    update_response = client.post(
        '/service/{}/template/{}'.format(sample_template.service_id, sample_template.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )

    assert update_response.status_code == 200
    update_json_resp = json.loads(update_response.get_data(as_text=True))
    assert update_json_resp['data']['content'] == (
        'my template has new content <script type="text/javascript">alert("foo")</script>'
    )
    assert update_json_resp['data']['name'] == sample_template.name
    assert update_json_resp['data']['template_type'] == sample_template.template_type
    assert update_json_resp['data']['version'] == 2


def test_should_be_able_to_archive_template(client, sample_template):
    data = {
        'name': sample_template.name,
        'template_type': sample_template.template_type,
        'content': sample_template.content,
        'archived': True,
        'service': str(sample_template.service.id),
        'created_by': str(sample_template.created_by.id)
    }

    json_data = json.dumps(data)

    auth_header = create_authorization_header()

    resp = client.post(
        '/service/{}/template/{}'.format(sample_template.service.id, sample_template.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=json_data
    )

    assert resp.status_code == 200
    assert Template.query.first().archived


def test_should_be_able_to_get_all_templates_for_a_service(client, sample_user, sample_service):
    data = {
        'name': 'my template 1',
        'template_type': EMAIL_TYPE,
        'subject': 'subject 1',
        'content': 'template content',
        'service': str(sample_service.id),
        'created_by': str(sample_user.id)
    }
    data_1 = json.dumps(data)
    data = {
        'name': 'my template 2',
        'template_type': EMAIL_TYPE,
        'subject': 'subject 2',
        'content': 'template content',
        'service': str(sample_service.id),
        'created_by': str(sample_user.id)
    }
    data_2 = json.dumps(data)
    auth_header = create_authorization_header()
    client.post(
        '/service/{}/template'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data_1
    )
    auth_header = create_authorization_header()

    client.post(
        '/service/{}/template'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data_2
    )

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template'.format(sample_service.id),
        headers=[auth_header]
    )

    assert response.status_code == 200
    update_json_resp = json.loads(response.get_data(as_text=True))
    assert update_json_resp['data'][0]['name'] == 'my template 1'
    assert update_json_resp['data'][0]['version'] == 1
    assert update_json_resp['data'][0]['created_at']
    assert update_json_resp['data'][1]['name'] == 'my template 2'
    assert update_json_resp['data'][1]['version'] == 1
    assert update_json_resp['data'][1]['created_at']


def test_should_get_only_templates_for_that_service(admin_request, notify_db_session):
    service_1 = create_service(service_name='service_1')
    service_2 = create_service(service_name='service_2')
    id_1 = create_template(service_1).id
    id_2 = create_template(service_1).id
    id_3 = create_template(service_2).id

    json_resp_1 = admin_request.get('template.get_all_templates_for_service', service_id=service_1.id)
    json_resp_2 = admin_request.get('template.get_all_templates_for_service', service_id=service_2.id)

    assert {template['id'] for template in json_resp_1['data']} == {str(id_1), str(id_2)}
    assert {template['id'] for template in json_resp_2['data']} == {str(id_3)}


@pytest.mark.parametrize(
    "subject, content, template_type", [
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            EMAIL_TYPE
        ),
        (
            None,
            'hello ((name)) we’ve received your ((thing))',
            SMS_TYPE
        ),
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            LETTER_TYPE
        )
    ]
)
def test_should_get_a_single_template(
    notify_db,
    client,
    sample_user,
    service_factory,
    subject,
    content,
    template_type
):

    template = create_sample_template(
        notify_db, notify_db.session, subject_line=subject, content=content, template_type=template_type
    )

    response = client.get(
        '/service/{}/template/{}'.format(template.service.id, template.id),
        headers=[create_authorization_header()]
    )

    data = json.loads(response.get_data(as_text=True))['data']

    assert response.status_code == 200
    assert data['content'] == content
    assert data['subject'] == subject
    assert data['process_type'] == 'normal'
    assert not data['redact_personalisation']


@pytest.mark.parametrize(
    "subject, content, path, expected_subject, expected_content, expected_error", [
        (
            'about your thing',
            'hello user we’ve received your thing',
            '/service/{}/template/{}/preview',
            'about your thing',
            'hello user we’ve received your thing',
            None
        ),
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            '/service/{}/template/{}/preview?name=Amala&thing=document',
            'about your document',
            'hello Amala we’ve received your document',
            None
        ),
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            '/service/{}/template/{}/preview?eman=Amala&gniht=document',
            None, None,
            'Missing personalisation: thing, name'
        ),
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            '/service/{}/template/{}/preview?name=Amala&thing=document&foo=bar',
            'about your document',
            'hello Amala we’ve received your document',
            None,
        )
    ]
)
def test_should_preview_a_single_template(
    notify_db,
    client,
    sample_user,
    service_factory,
    subject,
    content,
    path,
    expected_subject,
    expected_content,
    expected_error
):

    template = create_sample_template(
        notify_db, notify_db.session, subject_line=subject, content=content, template_type=EMAIL_TYPE
    )

    response = client.get(
        path.format(template.service.id, template.id),
        headers=[create_authorization_header()]
    )

    content = json.loads(response.get_data(as_text=True))

    if expected_error:
        assert response.status_code == 400
        assert content['message']['template'] == [expected_error]
    else:
        assert response.status_code == 200
        assert content['content'] == expected_content
        assert content['subject'] == expected_subject


def test_should_return_empty_array_if_no_templates_for_service(client, sample_service):

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template'.format(sample_service.id),
        headers=[auth_header]
    )

    assert response.status_code == 200
    json_resp = json.loads(response.get_data(as_text=True))
    assert len(json_resp['data']) == 0


def test_should_return_404_if_no_templates_for_service_with_id(client, sample_service, fake_uuid):

    auth_header = create_authorization_header()

    response = client.get(
        '/service/{}/template/{}'.format(sample_service.id, fake_uuid),
        headers=[auth_header]
    )

    assert response.status_code == 404
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['result'] == 'error'
    assert json_resp['message'] == 'No result found'


def test_create_400_for_over_limit_content(client, notify_api, sample_user, sample_service, fake_uuid):
    content = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(SMS_CHAR_COUNT_LIMIT + 1))
    data = {
        'name': 'too big template',
        'template_type': SMS_TYPE,
        'content': content,
        'service': str(sample_service.id),
        'created_by': str(sample_user.id)
    }
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    assert response.status_code == 400
    json_resp = json.loads(response.get_data(as_text=True))
    assert (
        'Content has a character count greater than the limit of {}'
    ).format(SMS_CHAR_COUNT_LIMIT) in json_resp['message']['content']


def test_update_400_for_over_limit_content(client, notify_api, sample_user, sample_template):
    json_data = json.dumps({
        'content': ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(
            SMS_CHAR_COUNT_LIMIT + 1)),
        'created_by': str(sample_user.id)
    })
    auth_header = create_authorization_header()
    resp = client.post(
        '/service/{}/template/{}'.format(sample_template.service.id, sample_template.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=json_data
    )
    assert resp.status_code == 400
    json_resp = json.loads(resp.get_data(as_text=True))
    assert (
        'Content has a character count greater than the limit of {}'
    ).format(SMS_CHAR_COUNT_LIMIT) in json_resp['message']['content']


def test_should_return_all_template_versions_for_service_and_template_id(client, sample_template):
    original_content = sample_template.content
    from app.dao.templates_dao import dao_update_template
    sample_template.content = original_content + '1'
    dao_update_template(sample_template)
    sample_template.content = original_content + '2'
    dao_update_template(sample_template)

    auth_header = create_authorization_header()
    resp = client.get('/service/{}/template/{}/versions'.format(sample_template.service_id, sample_template.id),
                      headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 200
    resp_json = json.loads(resp.get_data(as_text=True))['data']
    assert len(resp_json) == 3
    for x in resp_json:
        if x['version'] == 1:
            assert x['content'] == original_content
        elif x['version'] == 2:
            assert x['content'] == original_content + '1'
        else:
            assert x['content'] == original_content + '2'


def test_update_does_not_create_new_version_when_there_is_no_change(client, sample_template):

    auth_header = create_authorization_header()
    data = {
        'template_type': sample_template.template_type,
        'content': sample_template.content,
    }
    resp = client.post('/service/{}/template/{}'.format(sample_template.service_id, sample_template.id),
                       data=json.dumps(data),
                       headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 200

    template = dao_get_template_by_id(sample_template.id)
    assert template.version == 1


def test_update_set_process_type_on_template(client, sample_template):
    auth_header = create_authorization_header()
    data = {
        'process_type': 'priority'
    }
    resp = client.post('/service/{}/template/{}'.format(sample_template.service_id, sample_template.id),
                       data=json.dumps(data),
                       headers=[('Content-Type', 'application/json'), auth_header])
    assert resp.status_code == 200

    template = dao_get_template_by_id(sample_template.id)
    assert template.process_type == 'priority'


def test_create_a_template_with_reply_to(admin_request, sample_user):
    service = create_service(service_permissions=['letter'])
    letter_contact = create_letter_contact(service, "Edinburgh, ED1 1AA")
    data = {
        'name': 'my template',
        'subject': 'subject',
        'template_type': 'letter',
        'content': 'template <b>content</b>',
        'service': str(service.id),
        'created_by': str(sample_user.id),
        'reply_to': str(letter_contact.id),
    }

    json_resp = admin_request.post('template.create_template', service_id=service.id, _data=data, _expected_status=201)

    assert json_resp['data']['template_type'] == 'letter'
    assert json_resp['data']['reply_to'] == str(letter_contact.id)
    assert json_resp['data']['reply_to_text'] == letter_contact.contact_block

    template = Template.query.get(json_resp['data']['id'])
    from app.schemas import template_schema
    assert sorted(json_resp['data']) == sorted(template_schema.dump(template).data)
    th = TemplateHistory.query.filter_by(id=template.id, version=1).one()
    assert th.service_letter_contact_id == letter_contact.id


def test_create_a_template_with_foreign_service_reply_to(admin_request, sample_user):
    service = create_service(service_permissions=['letter'])
    service2 = create_service(service_name='test service', email_from='test@example.com',
                              service_permissions=['letter'])
    letter_contact = create_letter_contact(service2, "Edinburgh, ED1 1AA")
    data = {
        'name': 'my template',
        'subject': 'subject',
        'template_type': 'letter',
        'content': 'template <b>content</b>',
        'service': str(service.id),
        'created_by': str(sample_user.id),
        'reply_to': str(letter_contact.id),
    }

    json_resp = admin_request.post('template.create_template', service_id=service.id, _data=data, _expected_status=400)

    assert json_resp['message'] == "letter_contact_id {} does not exist in database for service id {}".format(
        str(letter_contact.id), str(service.id)
    )


@pytest.mark.parametrize('template_default, service_default',
                         [('template address', 'service address'),
                          (None, 'service address'),
                          ('template address', None),
                          (None, None)
                          ])
def test_get_template_reply_to(client, sample_service, template_default, service_default):
    auth_header = create_authorization_header()
    if service_default:
        create_letter_contact(
            service=sample_service, contact_block=service_default, is_default=True
        )
    if template_default:
        template_default_contact = create_letter_contact(
            service=sample_service, contact_block=template_default, is_default=False
        )
    reply_to_id = str(template_default_contact.id) if template_default else None
    template = create_template(service=sample_service, template_type='letter', reply_to=reply_to_id)

    resp = client.get('/service/{}/template/{}'.format(template.service_id, template.id),
                      headers=[auth_header])

    assert resp.status_code == 200, resp.get_data(as_text=True)
    json_resp = json.loads(resp.get_data(as_text=True))

    assert 'service_letter_contact_id' not in json_resp['data']
    assert json_resp['data']['reply_to'] == reply_to_id
    assert json_resp['data']['reply_to_text'] == template_default


def test_update_template_reply_to(client, sample_letter_template):
    auth_header = create_authorization_header()
    letter_contact = create_letter_contact(sample_letter_template.service, "Edinburgh, ED1 1AA")
    data = {
        'reply_to': str(letter_contact.id),
    }

    resp = client.post('/service/{}/template/{}'.format(sample_letter_template.service_id, sample_letter_template.id),
                       data=json.dumps(data),
                       headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 200, resp.get_data(as_text=True)

    template = dao_get_template_by_id(sample_letter_template.id)
    assert template.service_letter_contact_id == letter_contact.id
    th = TemplateHistory.query.filter_by(id=sample_letter_template.id, version=2).one()
    assert th.service_letter_contact_id == letter_contact.id


def test_update_template_reply_to_set_to_blank(client, notify_db_session):
    auth_header = create_authorization_header()
    service = create_service(service_permissions=['letter'])
    letter_contact = create_letter_contact(service, "Edinburgh, ED1 1AA")
    template = create_template(service=service, template_type='letter', reply_to=letter_contact.id)

    data = {
        'reply_to': None,
    }

    resp = client.post('/service/{}/template/{}'.format(template.service_id, template.id),
                       data=json.dumps(data),
                       headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 200, resp.get_data(as_text=True)

    template = dao_get_template_by_id(template.id)
    assert template.service_letter_contact_id is None
    th = TemplateHistory.query.filter_by(id=template.id, version=2).one()
    assert th.service_letter_contact_id is None


def test_update_template_with_foreign_service_reply_to(client, sample_letter_template):
    auth_header = create_authorization_header()

    service2 = create_service(service_name='test service', email_from='test@example.com',
                              service_permissions=['letter'])
    letter_contact = create_letter_contact(service2, "Edinburgh, ED1 1AA")

    data = {
        'reply_to': str(letter_contact.id),
    }

    resp = client.post('/service/{}/template/{}'.format(sample_letter_template.service_id, sample_letter_template.id),
                       data=json.dumps(data),
                       headers=[('Content-Type', 'application/json'), auth_header])

    assert resp.status_code == 400, resp.get_data(as_text=True)
    json_resp = json.loads(resp.get_data(as_text=True))

    assert json_resp['message'] == "letter_contact_id {} does not exist in database for service id {}".format(
        str(letter_contact.id), str(sample_letter_template.service_id)
    )


def test_update_redact_template(admin_request, sample_template):
    assert sample_template.redact_personalisation is False

    data = {
        'redact_personalisation': True,
        'created_by': str(sample_template.created_by_id)
    }

    dt = datetime.now()

    with freeze_time(dt):
        resp = admin_request.post(
            'template.update_template',
            service_id=sample_template.service_id,
            template_id=sample_template.id,
            _data=data
        )

    assert resp is None

    assert sample_template.redact_personalisation is True
    assert sample_template.template_redacted.updated_by_id == sample_template.created_by_id
    assert sample_template.template_redacted.updated_at == dt

    assert sample_template.version == 1


def test_update_redact_template_ignores_other_properties(admin_request, sample_template):
    data = {
        'name': 'Foo',
        'redact_personalisation': True,
        'created_by': str(sample_template.created_by_id)
    }

    admin_request.post(
        'template.update_template',
        service_id=sample_template.service_id,
        template_id=sample_template.id,
        _data=data
    )

    assert sample_template.redact_personalisation is True
    assert sample_template.name != 'Foo'


def test_update_redact_template_does_nothing_if_already_redacted(admin_request, sample_template):
    dt = datetime.now()
    with freeze_time(dt):
        dao_redact_template(sample_template, sample_template.created_by_id)

    data = {
        'redact_personalisation': True,
        'created_by': str(sample_template.created_by_id)
    }

    with freeze_time(dt + timedelta(days=1)):
        resp = admin_request.post(
            'template.update_template',
            service_id=sample_template.service_id,
            template_id=sample_template.id,
            _data=data
        )

    assert resp is None

    assert sample_template.redact_personalisation is True
    # make sure that it hasn't been updated
    assert sample_template.template_redacted.updated_at == dt


def test_update_redact_template_400s_if_no_created_by(admin_request, sample_template):
    original_updated_time = sample_template.template_redacted.updated_at
    resp = admin_request.post(
        'template.update_template',
        service_id=sample_template.service_id,
        template_id=sample_template.id,
        _data={'redact_personalisation': True},
        _expected_status=400
    )

    assert resp == {
        'result': 'error',
        'message': {'created_by': ['Field is required']}
    }

    assert sample_template.redact_personalisation is False
    assert sample_template.template_redacted.updated_at == original_updated_time


def test_preview_letter_template_by_id_invalid_file_type(
        sample_letter_notification,
        admin_request):

    resp = admin_request.get(
        'template.preview_letter_template_by_notification_id',
        service_id=sample_letter_notification.service_id,
        template_id=sample_letter_notification.template_id,
        notification_id=sample_letter_notification.id,
        file_type='doc',
        _expected_status=400
    )

    assert ['file_type must be pdf or png'] == resp['message']['content']


@freeze_time('2012-12-12')
@pytest.mark.parametrize('file_type', ('png', 'pdf'))
def test_preview_letter_template_by_id_valid_file_type(
    notify_api,
    sample_letter_notification,
    admin_request,
    file_type,
):
    sample_letter_notification.created_at = datetime.utcnow()
    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:
            content = b'\x00\x01'

            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/preview.{}'.format(file_type),
                content=content,
                headers={'X-pdf-page-count': '1'},
                status_code=200
            )

            resp = admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=sample_letter_notification.service_id,
                notification_id=sample_letter_notification.id,
                file_type=file_type,
            )

            post_json = mock_post.last_request.json()
            assert post_json['template']['id'] == str(sample_letter_notification.template_id)
            assert post_json['values'] == {
                'address_line_1': 'A1',
                'address_line_2': 'A2',
                'address_line_3': 'A3',
                'address_line_4': 'A4',
                'address_line_5': 'A5',
                'address_line_6': 'A6',
                'postcode': 'A_POST',
            }
            assert post_json['date'] == '2012-12-12T00:00:00'
            assert base64.b64decode(resp['content']) == content


def test_preview_letter_template_by_id_template_preview_500(
        notify_api,
        client,
        admin_request,
        sample_letter_notification):

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        import requests_mock
        with requests_mock.Mocker() as request_mock:
            content = b'\x00\x01'

            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/preview.pdf',
                content=content,
                headers={'X-pdf-page-count': '1'},
                status_code=404
            )

            resp = admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=sample_letter_notification.service_id,
                notification_id=sample_letter_notification.id,
                file_type='pdf',
                _expected_status=500
            )

            assert mock_post.last_request.json()
            assert 'Status code: 404' in resp['message']
            assert 'Error generating preview letter for {}'.format(sample_letter_notification.id) in resp['message']


def test_preview_letter_template_precompiled_pdf_file_type(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker():

            content = b'\x00\x01'

            mock_get_letter_pdf = mocker.patch('app.template.rest.get_letter_pdf', return_value=content)

            resp = admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=notification.service_id,
                notification_id=notification.id,
                file_type='pdf'
            )

            assert mock_get_letter_pdf.called_once_with(notification)
            assert base64.b64decode(resp['content']) == content


def test_preview_letter_template_precompiled_s3_error(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker():

            mocker.patch('app.template.rest.get_letter_pdf',
                         side_effect=botocore.exceptions.ClientError(
                             {'Error': {'Code': '403', 'Message': 'Unauthorized'}},
                             'GetObject'
                         ))

            request = admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=notification.service_id,
                notification_id=notification.id,
                file_type='pdf',
                _expected_status=500
            )

            assert request['message'] == "Error extracting requested page from PDF file for notification_id {} type " \
                                         "<class 'botocore.exceptions.ClientError'> An error occurred (403) " \
                                         "when calling the GetObject operation: Unauthorized".format(notification.id)


def test_preview_letter_template_precompiled_png_file_type(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:

            pdf_content = b'\x00\x01'
            png_content = b'\x00\x02'

            mock_get_letter_pdf = mocker.patch('app.template.rest.get_letter_pdf', return_value=pdf_content)

            mocker.patch('app.template.rest.extract_page_from_pdf', return_value=pdf_content)

            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/precompiled-preview.png',
                content=png_content,
                headers={'X-pdf-page-count': '1'},
                status_code=200
            )

            resp = admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=notification.service_id,
                notification_id=notification.id,
                file_type='png'
            )

            with pytest.raises(ValueError):
                mock_post.last_request.json()
            assert mock_get_letter_pdf.called_once_with(notification)
            assert base64.b64decode(resp['content']) == png_content


@pytest.mark.parametrize('page_number,expect_preview_url', [
    ('', 'http://localhost/notifications-template-preview/precompiled-preview.png?hide_notify=true'),
    ('1', 'http://localhost/notifications-template-preview/precompiled-preview.png?hide_notify=true'),
    ('2', 'http://localhost/notifications-template-preview/precompiled-preview.png')
])
def test_preview_letter_template_precompiled_png_file_type_hide_notify_tag_only_on_first_page(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker,
        page_number,
        expect_preview_url
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        pdf_content = b'\x00\x01'
        png_content = b'\x00\x02'
        encoded = base64.b64encode(png_content).decode('utf-8')

        mocker.patch('app.template.rest.get_letter_pdf', return_value=pdf_content)
        mocker.patch('app.template.rest.extract_page_from_pdf', return_value=png_content)
        mock_get_png_preview = mocker.patch('app.template.rest._get_png_preview', return_value=encoded)

        admin_request.get(
            'template.preview_letter_template_by_notification_id',
            service_id=notification.service_id,
            notification_id=notification.id,
            file_type='png',
            page=page_number
        )

        mock_get_png_preview.assert_called_once_with(
            expect_preview_url, encoded, notification.id, json=False
        )


def test_preview_letter_template_precompiled_png_template_preview_500_error(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:

            pdf_content = b'\x00\x01'
            png_content = b'\x00\x02'

            mocker.patch('app.template.rest.get_letter_pdf', return_value=pdf_content)

            mocker.patch('app.template.rest.extract_page_from_pdf', return_value=pdf_content)

            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/precompiled-preview.png',
                content=png_content,
                headers={'X-pdf-page-count': '1'},
                status_code=500
            )

            admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=notification.service_id,
                notification_id=notification.id,
                file_type='png',
                _expected_status=500

            )

            with pytest.raises(ValueError):
                mock_post.last_request.json()


def test_preview_letter_template_precompiled_png_template_preview_400_error(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:

            pdf_content = b'\x00\x01'
            png_content = b'\x00\x02'

            mocker.patch('app.template.rest.get_letter_pdf', return_value=pdf_content)

            mocker.patch('app.template.rest.extract_page_from_pdf', return_value=pdf_content)

            mock_post = request_mock.post(
                'http://localhost/notifications-template-preview/precompiled-preview.png',
                content=png_content,
                headers={'X-pdf-page-count': '1'},
                status_code=404
            )

            admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=notification.service_id,
                notification_id=notification.id,
                file_type='png',
                _expected_status=500
            )

            with pytest.raises(ValueError):
                mock_post.last_request.json()


def test_preview_letter_template_precompiled_png_template_preview_pdf_error(
        notify_api,
        client,
        admin_request,
        sample_service,
        mocker
):

    template = create_template(sample_service,
                               template_type='letter',
                               template_name='Pre-compiled PDF',
                               subject='Pre-compiled PDF',
                               hidden=True)

    notification = create_notification(template)

    with set_config_values(notify_api, {
        'TEMPLATE_PREVIEW_API_HOST': 'http://localhost/notifications-template-preview',
        'TEMPLATE_PREVIEW_API_KEY': 'test-key'
    }):
        with requests_mock.Mocker() as request_mock:

            pdf_content = b'\x00\x01'
            png_content = b'\x00\x02'

            mocker.patch('app.template.rest.get_letter_pdf', return_value=pdf_content)

            error_message = "PDF Error message"
            mocker.patch('app.template.rest.extract_page_from_pdf', side_effect=PdfReadError(error_message))

            request_mock.post(
                'http://localhost/notifications-template-preview/precompiled-preview.png',
                content=png_content,
                headers={'X-pdf-page-count': '1'},
                status_code=404
            )

            request = admin_request.get(
                'template.preview_letter_template_by_notification_id',
                service_id=notification.service_id,
                notification_id=notification.id,
                file_type='png',
                _expected_status=500
            )

            assert request['message'] == "Error extracting requested page from PDF file for notification_id {} type " \
                                         "{} {}".format(notification.id, type(PdfReadError()), error_message)
