import uuid

import pytest

from app.models import TemplateFolder

from tests.app.db import create_service, create_template_folder


def test_get_folders_for_service(admin_request, notify_db_session):
    s1 = create_service(service_name='a')
    s2 = create_service(service_name='b')

    tf1 = create_template_folder(s1)
    tf2 = create_template_folder(s1)

    create_template_folder(s2)

    resp = admin_request.get('template_folder.get_template_folders_for_service', service_id=s1.id)
    assert set(resp.keys()) == {'template_folders'}
    assert sorted(resp['template_folders'], key=lambda x: x['id']) == sorted([
        {'id': str(tf1.id), 'name': 'foo', 'service_id': str(s1.id), 'parent_id': None},
        {'id': str(tf2.id), 'name': 'foo', 'service_id': str(s1.id), 'parent_id': None},
    ], key=lambda x: x['id'])


def test_get_folders_for_service_with_no_folders(sample_service, admin_request):
    resp = admin_request.get('template_folder.get_template_folders_for_service', service_id=sample_service.id)
    assert resp == {'template_folders': []}


@pytest.mark.parametrize('has_parent', [True, False])
def test_create_template_folder(admin_request, sample_service, has_parent):
    existing_folder = create_template_folder(sample_service)

    parent_id = str(existing_folder.id) if has_parent else None

    resp = admin_request.post(
        'template_folder.create_template_folder',
        service_id=sample_service.id,
        _data={
            'name': 'foo',
            'parent_id': parent_id
        },
        _expected_status=201
    )

    assert resp['data']['name'] == 'foo'
    assert resp['data']['service_id'] == str(sample_service.id)
    assert resp['data']['parent_id'] == parent_id


@pytest.mark.parametrize('missing_field', ['name', 'parent_id'])
def test_create_template_folder_fails_if_missing_fields(admin_request, sample_service, missing_field):
    data = {
        'name': 'foo',
        'parent_id': None
    }
    data.pop(missing_field)

    resp = admin_request.post(
        'template_folder.create_template_folder',
        service_id=sample_service.id,
        _data=data,
        _expected_status=400
    )

    assert resp == {
        'status_code': 400,
        'errors': [
            {'error': 'ValidationError', 'message': '{} is a required property'.format(missing_field)}
        ]
    }


def test_create_template_folder_fails_if_unknown_parent_id(admin_request, sample_service):
    resp = admin_request.post(
        'template_folder.create_template_folder',
        service_id=sample_service.id,
        _data={'name': 'bar', 'parent_id': str(uuid.uuid4())},
        _expected_status=400
    )

    assert resp['result'] == 'error'
    assert resp['message'] == 'parent_id not found'


def test_create_template_folder_fails_if_parent_id_from_different_service(admin_request, sample_service):
    s1 = create_service(service_name='a')
    parent_folder_id = create_template_folder(s1).id

    resp = admin_request.post(
        'template_folder.create_template_folder',
        service_id=sample_service.id,
        _data={'name': 'bar', 'parent_id': str(parent_folder_id)},
        _expected_status=400
    )

    assert resp['result'] == 'error'
    assert resp['message'] == 'parent_id not found'


def test_rename_template_folder(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)

    resp = admin_request.post(
        'template_folder.rename_template_folder',
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _data={
            'name': 'bar'
        }
    )

    assert resp['data']['name'] == 'bar'
    assert existing_folder.name == 'bar'


@pytest.mark.parametrize('data, err', [
    ({}, 'name is a required property'),
    ({'name': None}, 'name None is not of type string'),
    ({'name': ''}, 'name  is too short'),
])
def test_rename_template_folder_fails_if_missing_name(admin_request, sample_service, data, err):
    existing_folder = create_template_folder(sample_service)

    resp = admin_request.post(
        'template_folder.rename_template_folder',
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _data=data,
        _expected_status=400
    )

    assert resp == {
        'status_code': 400,
        'errors': [
            {'error': 'ValidationError', 'message': err}
        ]
    }


def test_delete_template_folder(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)

    admin_request.delete(
        'template_folder.delete_template_folder',
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
    )

    assert TemplateFolder.query.all() == []


def test_delete_template_folder_fails_if_folder_has_subfolders(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)
    existing_subfolder = create_template_folder(sample_service, parent=existing_folder)  # noqa

    resp = admin_request.delete(
        'template_folder.delete_template_folder',
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _expected_status=400
    )

    assert resp == {
        'result': 'error',
        'message': 'Folder is not empty'
    }

    assert TemplateFolder.query.count() == 2


def test_delete_template_folder_fails_if_folder_contains_templates(admin_request, sample_service, sample_template):
    existing_folder = create_template_folder(sample_service)
    sample_template.folder = existing_folder

    resp = admin_request.delete(
        'template_folder.delete_template_folder',
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _expected_status=400
    )

    assert resp == {
        'result': 'error',
        'message': 'Folder is not empty'
    }

    assert TemplateFolder.query.count() == 1
