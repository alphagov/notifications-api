import json
import random
import string
from app.models import Template
from tests import create_authorization_header


def test_should_create_a_new_sms_template_for_a_service(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'sms',
                'content': 'template <b>content</b>',
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
            assert response.status_code == 201
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['data']['name'] == 'my template'
            assert json_resp['data']['template_type'] == 'sms'
            assert json_resp['data']['content'] == 'template content'
            assert json_resp['data']['service'] == str(sample_service.id)
            assert json_resp['data']['id']
            assert json_resp['data']['versions'] == [1]
            assert not json_resp['data']['subject']


def test_should_create_a_new_email_template_for_a_service(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
                'content': 'template <b>content</b>',
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
            assert response.status_code == 201
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['data']['name'] == 'my template'
            assert json_resp['data']['template_type'] == 'email'
            assert json_resp['data']['content'] == 'template content'
            assert json_resp['data']['service'] == str(sample_service.id)
            assert json_resp['data']['subject'] == 'subject'
            assert json_resp['data']['versions'] == [1]
            assert json_resp['data']['id']


def test_should_be_error_if_service_does_not_exist_on_create(notify_api, sample_user, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_should_error_if_created_by_missing(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_should_be_error_if_service_does_not_exist_on_update(notify_api, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_must_have_a_subject_on_an_email_template(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
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


def test_must_have_a_uniqe_subject_on_an_email_template(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
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
            assert response.status_code == 201

            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
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
            assert response.status_code == 400
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message']['subject'][0] == 'Duplicate template subject'


def test_should_be_able_to_update_a_template(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
                'content': 'template content',
                'service': str(sample_service.id),
                'created_by': str(sample_user.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header()

            create_response = client.post(
                '/service/{}/template'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            assert create_response.status_code == 201
            json_resp = json.loads(create_response.get_data(as_text=True))
            assert json_resp['data']['name'] == 'my template'
            data = {
                'content': 'my template has new content <script type="text/javascript">alert("foo")</script>',
                'created_by': str(sample_user.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header()

            update_response = client.post(
                '/service/{}/template/{}'.format(sample_service.id, json_resp['data']['id']),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )

            assert update_response.status_code == 200
            update_json_resp = json.loads(update_response.get_data(as_text=True))
            assert update_json_resp['data']['content'] == 'my template has new content alert("foo")'
            assert update_json_resp['data']['versions'] == [1, 2]


def test_should_be_able_to_archive_template(notify_api, sample_user, sample_service, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_should_be_able_to_get_all_templates_for_a_service(notify_api, sample_user, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
            assert update_json_resp['data'][0]['name'] == 'my template 1'
            assert update_json_resp['data'][0]['versions'] == [1]
            assert update_json_resp['data'][1]['name'] == 'my template 2'
            assert update_json_resp['data'][1]['versions'] == [1]


def test_should_get_only_templates_for_that_service(notify_api, sample_user, service_factory):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

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


def test_should_return_empty_array_if_no_templates_for_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template'.format(sample_service.id),
                headers=[auth_header]
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 0


def test_should_return_404_if_no_templates_for_service_with_id(notify_api, sample_service, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header()

            response = client.get(
                '/service/{}/template/{}'.format(sample_service.id, fake_uuid),
                headers=[auth_header]
            )

            assert response.status_code == 404
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'No result found'


def test_create_400_for_over_limit_content(notify_api, sample_user, sample_service, fake_uuid):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_update_400_for_over_limit_content(notify_api, sample_user, sample_template):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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


def test_should_return_all_template_versions_for_service_and_template_id(notify_api, sample_template):
    original_content = sample_template.content
    from app.dao.templates_dao import dao_update_template
    sample_template.content = original_content + '1'
    dao_update_template(sample_template)
    sample_template.content = original_content + '2'
    dao_update_template(sample_template)
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
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
