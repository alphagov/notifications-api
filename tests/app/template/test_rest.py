import json
import uuid

from tests import create_authorization_header


def test_should_create_a_new_sms_template_for_a_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'sms',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data
            )

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
            assert not json_resp['data']['subject']


def test_should_create_a_new_email_template_for_a_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data
            )

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
            assert json_resp['data']['id']


def test_should_be_error_if_service_does_not_exist_on_create(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            bad_id = str(uuid.uuid4())
            data = {
                'name': 'my template',
                'template_type': 'sms',
                'content': 'template content',
                'service': bad_id
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(bad_id),
                method='POST',
                request_body=data
            )

            response = client.post(
                '/service/{}/template'.format(bad_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Service not found'


def test_should_be_error_if_service_does_not_exist_on_update(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            bad_id = str(uuid.uuid4())
            data = {
                'name': 'my template'
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template/123'.format(bad_id),
                method='POST',
                request_body=data
            )

            response = client.post(
                '/service/{}/template/123'.format(bad_id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 404
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Template not found'


def test_must_have_a_subject_on_an_email_template(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data
            )

            response = client.post(
                '/service/{}/template'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 500
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Failed to create template'


def test_must_have_a_uniqe_subject_on_an_email_template(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data
            )

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
                'service': str(sample_service.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data
            )

            response = client.post(
                '/service/{}/template'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            assert response.status_code == 400
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Duplicate template subject'


def test_should_be_able_to_update_a_template(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template',
                'template_type': 'email',
                'subject': 'subject',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data
            )

            create_response = client.post(
                '/service/{}/template'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )
            assert create_response.status_code == 201
            json_resp = json.loads(create_response.get_data(as_text=True))
            assert json_resp['data']['name'] == 'my template'
            data = {
                'name': 'my template has a new name'
            }
            data = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template/{}'.format(sample_service.id, json_resp['data']['id']),
                method='POST',
                request_body=data
            )

            update_response = client.post(
                '/service/{}/template/{}'.format(sample_service.id, json_resp['data']['id']),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data
            )

            assert update_response.status_code == 200
            update_json_resp = json.loads(update_response.get_data(as_text=True))
            assert update_json_resp['data']['name'] == 'my template has a new name'


def test_should_be_able_to_get_all_templates_for_a_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'name': 'my template 1',
                'template_type': 'email',
                'subject': 'subject 1',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data_1 = json.dumps(data)
            data = {
                'name': 'my template 2',
                'template_type': 'email',
                'subject': 'subject 2',
                'content': 'template content',
                'service': str(sample_service.id)
            }
            data_2 = json.dumps(data)
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data_1
            )
            client.post(
                '/service/{}/template'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data_1
            )
            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='POST',
                request_body=data_2
            )

            client.post(
                '/service/{}/template'.format(sample_service.id),
                headers=[('Content-Type', 'application/json'), auth_header],
                data=data_2
            )

            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='GET'
            )

            response = client.get(
                '/service/{}/template'.format(sample_service.id),
                headers=[auth_header]
            )

            assert response.status_code == 200
            update_json_resp = json.loads(response.get_data(as_text=True))
            assert update_json_resp['data'][0]['name'] == 'my template 1'
            assert update_json_resp['data'][1]['name'] == 'my template 2'


def test_should_get_only_templates_for_that_servcie(notify_api, service_factory):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            service_1 = service_factory.get('service 1')
            service_2 = service_factory.get('service 2')

            auth_header_1 = create_authorization_header(
                path='/service/{}/template'.format(service_1.id),
                method='GET'
            )

            response_1 = client.get(
                '/service/{}/template'.format(service_1.id),
                headers=[auth_header_1]
            )

            auth_header_2 = create_authorization_header(
                path='/service/{}/template'.format(service_2.id),
                method='GET'
            )

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
                'service': str(service_1.id)
            }
            data = json.dumps(data)
            create_auth_header = create_authorization_header(
                path='/service/{}/template'.format(service_1.id),
                method='POST',
                request_body=data
            )
            client.post(
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

            auth_header = create_authorization_header(
                path='/service/{}/template'.format(sample_service.id),
                method='GET'
            )

            response = client.get(
                '/service/{}/template'.format(sample_service.id),
                headers=[auth_header]
            )

            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 0


def test_should_return_404_if_no_templates_for_service_with_id(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            auth_header = create_authorization_header(
                path='/service/{}/template/{}'.format(sample_service.id, 111),
                method='GET'
            )

            response = client.get(
                '/service/{}/template/{}'.format(sample_service.id, 111),
                headers=[auth_header]
            )

            assert response.status_code == 404
            json_resp = json.loads(response.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'Template not found'
