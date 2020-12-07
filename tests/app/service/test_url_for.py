import uuid

from flask import url_for

service_id = str(uuid.uuid4())


def test_url_for_get_services(notify_api):
    with notify_api.test_request_context():
        url = url_for('service.get_services')
        assert str(url) == '/service'
        url_with_user_id = url_for('service.get_services', user_id=1)
        assert str(url_with_user_id) == '/service?user_id=1'


def test_url_for_get_service_by_id(notify_api):
    with notify_api.test_request_context():
        url = url_for('service.get_service_by_id', service_id=service_id)
        assert str(url) == '/service/{}'.format(service_id)

        url_with_user_id = url_for('service.get_service_by_id', service_id=service_id, user_id=1)
        assert str(url_with_user_id) == '/service/{0}?user_id={1}'.format(service_id, 1)


def test_url_for_create_service(notify_api):
    with notify_api.test_request_context():
        url = url_for('service.create_service')
        assert str(url) == '/service'


def test_url_for_update_service(notify_api):
    with notify_api.test_request_context():
        url = url_for('service.update_service', service_id=service_id)
        assert str(url) == '/service/{}'.format(service_id)


def test_url_for_create_api_key(notify_api):
    with notify_api.test_request_context():
        url = url_for('service.create_api_key', service_id=service_id)
        assert str(url) == '/service/{}/api-key'.format(service_id)
