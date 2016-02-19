import json
import uuid
from flask import url_for

from app.dao.users_dao import save_model_user
from app.models import User, Template, Service
from tests import create_authorization_header


def test_get_service_list(notify_api, service_factory):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_factory.get('one')
            service_factory.get('two')
            service_factory.get('three')

            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
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


def test_get_service_list_by_user(notify_api, service_factory, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_factory.get('one', sample_user)
            service_factory.get('two', sample_user)
            service_factory.get('three', sample_user)

            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service?user_id='.format(sample_user.id),
                headers=[auth_header]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(json_resp['data']) == 3
            assert json_resp['data'][0]['name'] == 'one'
            assert json_resp['data'][1]['name'] == 'two'
            assert json_resp['data'][2]['name'] == 'three'


def test_get_service_list_by_user_should_return_empty_list_if_no_services(notify_api, service_factory, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            new_user = User(
                name='Test User',
                email_address='new_user@digital.cabinet-office.gov.uk',
                password='password',
                mobile_number='+447700900986'
            )
            save_model_user(new_user)

            service_factory.get('one', sample_user)
            service_factory.get('two', sample_user)
            service_factory.get('three', sample_user)

            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service?user_id={}'.format(new_user.id),
                headers=[auth_header]
            )
            json_resp = json.loads(response.get_data(as_text=True))
            assert response.status_code == 200
            assert len(json_resp['data']) == 0


def test_get_service_list_should_return_empty_list_if_no_services(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                path='/service',
                method='GET'
            )
            response = client.get(
                '/service',
                headers=[auth_header]
            )
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 0


def test_get_service_by_id(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='GET'
            )
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_service.name
            assert json_resp['data']['id'] == str(sample_service.id)


def test_get_service_by_id_should_404_if_no_service(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_authorization_header(
                path='/service/{}'.format(service_id),
                method='GET'
            )
            resp = client.get(
                '/service/{}'.format(service_id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'not found'


def test_get_service_by_id_and_user(notify_api, service_factory, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service = service_factory.get('new service', sample_user)
            auth_header = create_authorization_header(
                path='/service/{}'.format(service.id),
                method='GET'
            )
            resp = client.get(
                '/service/{}?user_id={}'.format(service.id, sample_user.id),
                headers=[auth_header]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == service.name
            assert json_resp['data']['id'] == str(service.id)


def test_get_service_by_id_should_404_if_no_service_for_user(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            service_id = str(uuid.uuid4())
            auth_header = create_authorization_header(
                path='/service/{}'.format(service_id),
                method='GET'
            )
            resp = client.get(
                '/service/{}?user_id={}'.format(service_id, sample_user.id),
                headers=[auth_header]
            )
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['result'] == 'error'
            assert json_resp['message'] == 'not found'


def test_create_service(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'user_id': sample_user.id,
                'limit': 1000,
                'restricted': False,
                'active': False}
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 201
            assert json_resp['data']['id']
            assert json_resp['data']['name'] == 'created service'

            auth_header_fetch = create_authorization_header(
                path='/service/{}'.format(json_resp['data']['id']),
                method='GET'
            )

            resp = client.get(
                '/service/{}?user_id={}'.format(json_resp['data']['id'], sample_user.id),
                headers=[auth_header_fetch]
            )
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == 'created service'


def test_should_not_create_service_with_missing_user_id_field(notify_api):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'name': 'created service',
                'limit': 1000,
                'restricted': False,
                'active': False
            }
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['user_id']


def test_should_not_create_service_with_missing_if_user_id_is_not_in_database(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'email_from': 'service',
                'user_id': 1234,
                'name': 'created service',
                'limit': 1000,
                'restricted': False,
                'active': False
            }
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'not found' in json_resp['message']['user_id']


def test_should_not_create_service_with_missing_if_missing_data(notify_api, sample_user):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            data = {
                'user_id': sample_user.id
            }
            auth_header = create_authorization_header(
                path='/service',
                method='POST',
                request_body=json.dumps(data)
            )
            headers = [('Content-Type', 'application/json'), auth_header]
            resp = client.post(
                '/service',
                data=json.dumps(data),
                headers=headers)
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 400
            assert json_resp['result'] == 'error'
            assert 'Missing data for required field.' in json_resp['message']['name']
            assert 'Missing data for required field.' in json_resp['message']['active']
            assert 'Missing data for required field.' in json_resp['message']['limit']
            assert 'Missing data for required field.' in json_resp['message']['restricted']
            assert 'Missing data for required field.' in json_resp['message']['email_from']


def test_update_service(notify_api, sample_service):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='GET'
            )
            resp = client.get(
                '/service/{}'.format(sample_service.id),
                headers=[auth_header]
            )
            json_resp = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert json_resp['data']['name'] == sample_service.name

            data = {
                'name': 'updated service name'
            }

            auth_header = create_authorization_header(
                path='/service/{}'.format(sample_service.id),
                method='POST',
                request_body=json.dumps(data)
            )

            resp = client.post(
                '/service/{}'.format(sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            result = json.loads(resp.get_data(as_text=True))
            assert resp.status_code == 200
            assert result['data']['name'] == 'updated service name'


def test_update_service_should_404_if_id_is_invalid(notify_api, notify_db):
    with notify_api.test_request_context():
        with notify_api.test_client() as client:

            data = {
                'name': 'updated service name'
            }

            missing_service_id = uuid.uuid4()

            auth_header = create_authorization_header(
                path='/service/{}'.format(missing_service_id),
                method='POST',
                request_body=json.dumps(data)
            )

            resp = client.post(
                '/service/{}'.format(missing_service_id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header]
            )
            assert resp.status_code == 404


def test_create_template(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests POST endpoint '/<service_id>/template' a template can be created
    from a service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Template.query.count() == 0
            template_name = "template name"
            template_type = "sms"
            template_content = "This is a template"
            data = {
                'name': template_name,
                'template_type': template_type,
                'content': template_content,
                'service': str(sample_service.id)
            }
            auth_header = create_authorization_header(path=url_for('service.create_template',
                                                                   service_id=sample_service.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            resp = client.post(
                url_for('service.create_template', service_id=sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 201
            assert Template.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == template_name
            assert json_resp['data']['template_type'] == template_type
            assert json_resp['data']['content'] == template_content


def test_create_template_service_not_exists(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests POST endpoint '/<service_id>/template' a template can be created
    from a service.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Template.query.count() == 0
            template_name = "template name"
            template_type = "sms"
            template_content = "This is a template"
            data = {
                'name': template_name,
                'template_type': template_type,
                'content': template_content,
                'service': str(sample_service.id)
            }
            missing_service_id = uuid.uuid4()
            auth_header = create_authorization_header(path=url_for('service.create_template',
                                                                   service_id=missing_service_id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            resp = client.post(
                url_for('service.create_template', service_id=missing_service_id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            assert Template.query.count() == 0
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "Service not found" in json_resp['message']


def test_update_template(notify_api, notify_db, notify_db_session, sample_template):
    """
    Tests PUT endpoint '/<service_id>/template/<template_id>' a template can be
    updated.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Template.query.count() == 1
            sample_service = Service.query.first()
            old_name = sample_template.name
            template_name = "new name"
            template_type = "sms"
            template_content = "content has been changed"
            data = {
                'name': template_name,
                'template_type': template_type,
                'content': template_content,
                'service': str(sample_service.id)
            }
            auth_header = create_authorization_header(path=url_for('service.update_template',
                                                                   service_id=sample_service.id,
                                                                   template_id=sample_template.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            resp = client.put(
                url_for('service.update_template',
                        service_id=sample_service.id,
                        template_id=sample_template.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 200
            assert Template.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == template_name
            assert json_resp['data']['template_type'] == template_type
            assert json_resp['data']['content'] == template_content
            assert old_name != template_name


def test_update_template_service_not_exists(notify_api, notify_db, notify_db_session,
                                            sample_template):
    """
    Tests PUT endpoint '/<service_id>/template/<template_id>' a 404 if service
    doesn't exist.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Template.query.count() == 1
            template_name = "new name"
            template_type = "sms"
            template_content = "content has been changed"
            data = {
                'name': template_name,
                'template_type': template_type,
                'content': template_content,
                'service': str(sample_template.service_id)
            }
            missing_service_id = uuid.uuid4()
            auth_header = create_authorization_header(path=url_for('service.update_template',
                                                                   service_id=missing_service_id,
                                                                   template_id=sample_template.id),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            resp = client.put(
                url_for('service.update_template',
                        service_id=missing_service_id,
                        template_id=sample_template.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "Service not found" in json_resp['message']
            assert template_name != sample_template.name


def test_update_template_template_not_exists(notify_api, notify_db, notify_db_session,
                                             sample_template):
    """
    Tests PUT endpoint '/<service_id>/template/<template_id>' a 404 if template
    doesn't exist.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Template.query.count() == 1
            sample_service = Service.query.first()
            template_name = "new name"
            template_type = "sms"
            template_content = "content has been changed"
            data = {
                'name': template_name,
                'template_type': template_type,
                'content': template_content,
                'service': str(sample_service.id)
            }
            auth_header = create_authorization_header(path=url_for('service.update_template',
                                                                   service_id=sample_service.id,
                                                                   template_id="123"),
                                                      method='PUT',
                                                      request_body=json.dumps(data))
            resp = client.put(
                url_for('service.update_template',
                        service_id=sample_service.id,
                        template_id="123"),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 404
            json_resp = json.loads(resp.get_data(as_text=True))
            assert "Template not found" in json_resp['message']
            assert template_name != sample_template.name


def test_create_template_unicode_content(notify_api, notify_db, notify_db_session, sample_service):
    """
    Tests POST endpoint '/<service_id>/template/<template_id>' a template is
    created and the content encoding is respected after saving and loading
    from the db.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            assert Template.query.count() == 0
            template_name = "template name"
            template_type = "sms"
            template_content = 'Россия'
            data = {
                'name': template_name,
                'template_type': template_type,
                'content': template_content,
                'service': str(sample_service.id)
            }
            auth_header = create_authorization_header(path=url_for('service.create_template',
                                                                   service_id=sample_service.id),
                                                      method='POST',
                                                      request_body=json.dumps(data))
            resp = client.post(
                url_for('service.create_template', service_id=sample_service.id),
                data=json.dumps(data),
                headers=[('Content-Type', 'application/json'), auth_header])
            assert resp.status_code == 201
            assert Template.query.count() == 1
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == template_name
            assert json_resp['data']['template_type'] == template_type
            assert json_resp['data']['content'] == template_content


def test_get_template_list(notify_api, notify_db, notify_db_session, sample_template):
    """
    Tests GET endpoint '/' to retrieve entire template list.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_template.service_id,
                path=url_for(
                    'service.get_service_template',
                    service_id=sample_template.service_id),
                method='GET')
            response = client.get(
                url_for(
                    'service.get_service_template',
                    service_id=sample_template.service_id),
                headers=[auth_header])
            assert response.status_code == 200
            json_resp = json.loads(response.get_data(as_text=True))
            assert len(json_resp['data']) == 1
            assert json_resp['data'][0]['name'] == sample_template.name
            assert json_resp['data'][0]['id'] == sample_template.id


def test_get_template(notify_api, notify_db, notify_db_session, sample_template):
    """
    Tests GET endpoint '/<template_id>' to retrieve a single template.
    """
    with notify_api.test_request_context():
        with notify_api.test_client() as client:
            auth_header = create_authorization_header(
                service_id=sample_template.service_id,
                path=url_for(
                    'service.get_service_template',
                    template_id=sample_template.id,
                    service_id=sample_template.service_id),
                method='GET')
            resp = client.get(url_for(
                'service.get_service_template',
                template_id=sample_template.id,
                service_id=sample_template.service_id),
                headers=[auth_header])
            assert resp.status_code == 200
            json_resp = json.loads(resp.get_data(as_text=True))
            assert json_resp['data']['name'] == sample_template.name
            assert json_resp['data']['id'] == sample_template.id
