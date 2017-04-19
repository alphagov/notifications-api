import pytest

from flask import json

from app.models import TEMPLATE_TYPES, EMAIL_TYPE
from tests import create_authorization_header
from tests.app.db import create_template


def test_get_all_templates_returns_200(client, sample_service):
    num_templates = 3
    templates = []
    for i in range(num_templates):
        for tmp_type in TEMPLATE_TYPES:
            subject = 'subject_{}'.format(i) if tmp_type == EMAIL_TYPE else ''
            templates.append(create_template(sample_service, template_type=tmp_type, subject=subject))

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates',
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == num_templates * len(TEMPLATE_TYPES)

    # need to reverse index as get all templates returns list sorted by descending date
    for i in range(len(json_response['templates'])):
        reverse_index = len(json_response['templates']) - 1 - i
        assert json_response['templates'][reverse_index]['id'] == str(templates[i].id)
        assert json_response['templates'][reverse_index]['body'] == templates[i].content
        assert json_response['templates'][reverse_index]['type'] == templates[i].template_type
        if templates[i].template_type == EMAIL_TYPE:
            assert json_response['templates'][reverse_index]['subject'] == templates[i].subject


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_all_templates_for_valid_type_returns_200(client, sample_service, tmp_type):
    num_templates = 3
    templates = []
    for i in range(num_templates):
        subject = 'subject_{}'.format(i) if tmp_type == EMAIL_TYPE else ''
        templates.append(create_template(sample_service, template_type=tmp_type, subject=subject))

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates?type={}'.format(tmp_type),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == num_templates

    # need to reverse index as get all templates returns list sorted by descending date
    for i in range(len(json_response['templates'])):
        reverse_index = len(json_response['templates']) - 1 - i
        assert json_response['templates'][reverse_index]['id'] == str(templates[i].id)
        assert json_response['templates'][reverse_index]['body'] == templates[i].content
        assert json_response['templates'][reverse_index]['type'] == tmp_type
        if templates[i].template_type == EMAIL_TYPE:
            assert json_response['templates'][reverse_index]['subject'] == templates[i].subject


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_correct_num_templates_for_valid_type_returns_200(client, sample_service, tmp_type):
    num_templates = 3

    templates = []
    for i in range(num_templates):
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
                'message': 'type coconut is not one of [sms, email, letter]',
                'error': 'ValidationError'
            }
        ]
    }
