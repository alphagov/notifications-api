import pytest

from flask import json
from itertools import product

from app.models import TEMPLATE_TYPES, EMAIL_TYPE
from tests import create_authorization_header
from tests.app.db import create_template


def test_get_all_templates_returns_200(client, sample_service):
    templates = [
        create_template(
            sample_service,
            template_type=tmp_type,
            subject='subject_{}'.format(name) if tmp_type == EMAIL_TYPE else '',
            template_name=name,
        )
        for name, tmp_type in product(('A', 'B', 'C'), TEMPLATE_TYPES)
    ]

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates',
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == len(templates)

    for index, template in enumerate(json_response['templates']):
        assert template['id'] == str(templates[index].id)
        assert template['body'] == templates[index].content
        assert template['type'] == templates[index].template_type
        if templates[index].template_type == EMAIL_TYPE:
            assert template['subject'] == templates[index].subject


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_all_templates_for_valid_type_returns_200(client, sample_service, tmp_type):
    templates = [
        create_template(
            sample_service,
            template_type=tmp_type,
            template_name='Template {}'.format(i),
            subject='subject_{}'.format(i) if tmp_type == EMAIL_TYPE else ''
        )
        for i in range(3)
    ]

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates?type={}'.format(tmp_type),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == len(templates)

    for index, template in enumerate(json_response['templates']):
        assert template['id'] == str(templates[index].id)
        assert template['body'] == templates[index].content
        assert template['type'] == tmp_type
        if templates[index].template_type == EMAIL_TYPE:
            assert template['subject'] == templates[index].subject


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_correct_num_templates_for_valid_type_returns_200(client, sample_service, tmp_type):
    num_templates = 3

    templates = []
    for _ in range(num_templates):
        templates.append(create_template(sample_service, template_type=tmp_type))

    for other_type in TEMPLATE_TYPES:
        if other_type != tmp_type:
            templates.append(create_template(sample_service, template_type=other_type))

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates?type={}'.format(tmp_type),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == num_templates


def test_get_all_templates_for_invalid_type_returns_400(client, sample_service):
    auth_header = create_authorization_header(service_id=sample_service.id)

    invalid_type = 'coconut'

    response = client.get(path='/v2/templates?type={}'.format(invalid_type),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 400
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert json_response == {
        'status_code': 400,
        'errors': [
            {
                'message': 'type coconut is not one of [sms, email, letter, broadcast]',
                'error': 'ValidationError'
            }
        ]
    }
