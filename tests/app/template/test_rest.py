import pytest
import json
import random
import string
import pytest
from app.models import Template
from tests import create_authorization_header
from tests.app.conftest import sample_template as create_sample_template
from app.dao.templates_dao import dao_get_template_by_id


@pytest.mark.parametrize('template_type, subject', [
    ('sms', None),
    ('email', 'subject'),
    ('letter', 'subject'),
])
def test_should_create_a_new_template_for_a_service(
    client, sample_user, sample_service, template_type, subject
):
    data = {
        'name': 'my template',
        'template_type': template_type,
        'content': 'template <b>content</b>',
        'service': str(sample_service.id),
        'created_by': str(sample_user.id)
    }
    if subject:
        data.update({'subject': subject})
    data = json.dumps(data)
    auth_header = create_authorization_header()

    response = client.post(
        '/service/{}/template'.format(sample_service.id),
        headers=[('Content-Type', 'application/json'), auth_header],
        data=data
    )
    assert response.status_code == 201
    json_resp = json.loads(response.get_data(as_text=True))
    assert json_resp['data']['name'] == 'my template'
    assert json_resp['data']['template_type'] == template_type
    assert json_resp['data']['content'] == 'template content'
    assert json_resp['data']['service'] == str(sample_service.id)
    assert json_resp['data']['id']
    assert json_resp['data']['version'] == 1
    if subject:
        assert json_resp['data']['subject'] == 'subject'
    else:
        assert not json_resp['data']['subject']


def test_should_be_error_if_service_does_not_exist_on_create(client, sample_user, fake_uuid):
    data = {
        'name': 'my template',
        'template_type': 'sms',
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


def test_should_error_if_created_by_missing(client, sample_user, sample_service):
    service_id = str(sample_service.id)
    data = {
        'name': 'my template',
        'template_type': 'sms',
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


@pytest.mark.parametrize('template_type', ['email', 'letter'])
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
    assert update_json_resp['data']['content'] == 'my template has new content alert("foo")'
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
        'template_type': 'email',
        'subject': 'subject 1',
        'content': 'template content',
        'service': str(sample_service.id),
        'created_by': str(sample_user.id)
    }
    data_1 = json.dumps(data)
    data = {
        'name': 'my template 2',
        'template_type': 'email',
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
    assert update_json_resp['data'][0]['name'] == 'my template 2'
    assert update_json_resp['data'][0]['version'] == 1
    assert update_json_resp['data'][0]['created_at']
    assert update_json_resp['data'][1]['name'] == 'my template 1'
    assert update_json_resp['data'][1]['version'] == 1
    assert update_json_resp['data'][1]['created_at']


def test_should_get_only_templates_for_that_service(client, sample_user, service_factory):

    service_1 = service_factory.get('service 1', email_from='service.1')
    service_2 = service_factory.get('service 2', email_from='service.2')

    auth_header_1 = create_authorization_header()

    response_1 = client.get(
        '/service/{}/template'.format(service_1.id),
        headers=[auth_header_1]
    )

    auth_header_2 = create_authorization_header()

    response_2 = client.get(
        '/service/{}/template'.format(service_2.id),
        headers=[auth_header_2]
    )

    assert response_1.status_code == 200
    assert response_2.status_code == 200

    json_resp_1 = json.loads(response_1.get_data(as_text=True))
    json_resp_2 = json.loads(response_2.get_data(as_text=True))

    assert len(json_resp_1['data']) == 1
    assert len(json_resp_2['data']) == 1

    data = {
        'name': 'my template 2',
        'template_type': 'email',
        'subject': 'subject 2',
        'content': 'template content',
        'service': str(service_1.id),
        'created_by': str(sample_user.id)
    }
    data = json.dumps(data)
    create_auth_header = create_authorization_header()
    resp = client.post(
        '/service/{}/template'.format(service_1.id),
        headers=[('Content-Type', 'application/json'), create_auth_header],
        data=data
    )

    response_3 = client.get(
        '/service/{}/template'.format(service_1.id),
        headers=[auth_header_1]
    )

    response_4 = client.get(
        '/service/{}/template'.format(service_2.id),
        headers=[auth_header_2]
    )

    assert response_3.status_code == 200
    assert response_4.status_code == 200

    json_resp_3 = json.loads(response_3.get_data(as_text=True))
    json_resp_4 = json.loads(response_4.get_data(as_text=True))

    assert len(json_resp_3['data']) == 2
    assert len(json_resp_4['data']) == 1


@pytest.mark.parametrize(
    "subject, content, template_type", [
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            'email'
        ),
        (
            None,
            'hello ((name)) we’ve received your ((thing))',
            'sms'
        ),
        (
            'about your ((thing))',
            'hello ((name)) we’ve received your ((thing))',
            'letter'
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
            None, None,
            'Personalisation not needed for template: foo'
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
        notify_db, notify_db.session, subject_line=subject, content=content, template_type='email'
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

    limit = notify_api.config.get('SMS_CHAR_COUNT_LIMIT')
    content = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(limit + 1))
    data = {
        'name': 'too big template',
        'template_type': 'sms',
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
    ).format(limit) in json_resp['message']['content']


def test_update_400_for_over_limit_content(client, notify_api, sample_user, sample_template):

    limit = notify_api.config.get('SMS_CHAR_COUNT_LIMIT')
    json_data = json.dumps({
        'content': ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(limit + 1)),
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
    ).format(limit) in json_resp['message']['content']


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
