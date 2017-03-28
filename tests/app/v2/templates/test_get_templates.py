import pytest

from flask import json

from app import DATETIME_FORMAT
from app.models import EMAIL_TYPE, SMS_TYPE, LETTER_TYPE, TEMPLATE_TYPES
from tests import create_authorization_header
from tests.app.db import create_template


def test_get_all_templates(client, sample_service):
    num_templates = 3
    templates = []
    for i in range(num_templates):
        for tmp_type in TEMPLATE_TYPES:
            templates.append(create_template(sample_service, template_type=tmp_type))

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates/?',
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == num_templates * len(TEMPLATE_TYPES)

    # need to reverse index as get all templates returns list sorted by descending date
    for i in range(len(json_response['templates'])):
        reverse_index = len(json_response['templates']) - 1 - i
        assert json_response['templates'][reverse_index]['id'] == str(templates[i].id)
        assert json_response['templates'][reverse_index]['body'] == templates[i].content
        assert json_response['templates'][reverse_index]['type'] == templates[i].template_type


@pytest.mark.parametrize("tmp_type", TEMPLATE_TYPES)
def test_get_all_templates_for_type(client, sample_service, tmp_type):
    num_templates = 3
    templates = []
    for i in range(num_templates):
        templates.append(create_template(sample_service, template_type=tmp_type))

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates/?type={}'.format(tmp_type),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == num_templates

    # need to reverse index as get all templates returns list sorted by descending date
    for i in range(len(json_response['templates'])):
        reverse_index = len(json_response['templates']) - 1 - i
        assert json_response['templates'][reverse_index]['id'] == str(templates[i].id)
        assert json_response['templates'][reverse_index]['body'] == templates[i].content
        assert json_response['templates'][reverse_index]['type'] == templates[i].template_type


@pytest.mark.parametrize("tmp_type", [EMAIL_TYPE, SMS_TYPE])
def test_get_all_templates_older_than_parameter(client, sample_service, tmp_type):
    num_templates = 5
    templates = []
    for i in range(num_templates):
        template = create_template(sample_service, template_type=tmp_type)
        templates.append(template)

    num_templates_older = 3

    # only get the first #num_templates_older templates
    older_than_id = templates[num_templates_older].id

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates/?type={}&older_than={}'.format(tmp_type, older_than_id),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == num_templates_older

    # need to reverse index as get all templates returns list sorted by descending date
    for i in range(num_templates_older):
        reverse_index = num_templates_older - 1 - i
        assert json_response['templates'][reverse_index]['id'] == str(templates[i].id)
        assert json_response['templates'][reverse_index]['body'] == templates[i].content
        assert json_response['templates'][reverse_index]['type'] == templates[i].template_type

    assert str(older_than_id) in json_response['links']['current']
    assert str(templates[0].id) in json_response['links']['next']


@pytest.mark.parametrize("tmp_type", [EMAIL_TYPE, SMS_TYPE])
def test_get_all_templates_none_existent_older_than_parameter(client, sample_service, tmp_type, fake_uuid):
    num_templates = 2
    templates = []
    for i in range(num_templates):
        template = create_template(sample_service, template_type=tmp_type)
        templates.append(template)

    auth_header = create_authorization_header(service_id=sample_service.id)

    response = client.get(path='/v2/templates/?type={}&older_than={}'.format(tmp_type, fake_uuid),
                          headers=[('Content-Type', 'application/json'), auth_header])

    assert response.status_code == 200
    assert response.headers['Content-type'] == 'application/json'

    json_response = json.loads(response.get_data(as_text=True))

    assert len(json_response['templates']) == 0
