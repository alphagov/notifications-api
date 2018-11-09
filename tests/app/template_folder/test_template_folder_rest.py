import uuid

import pytest

from app.models import TemplateFolder

from tests.app.db import create_service, create_template_folder, create_template


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


@pytest.mark.parametrize('data', [
    {},
    {'templates': None, 'folders': []},
    {'folders': []},
    {'templates': [], 'folders': [None]},
    {'templates': [], 'folders': ['not a uuid']},
])
def test_move_to_folder_validates_schema(data, admin_request, notify_db_session):
    admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=uuid.uuid4(),
        target_template_folder_id=uuid.uuid4(),
        _data=data,
        _expected_status=400
    )


def test_move_to_folder_moves_folders_and_templates(admin_request, sample_service):
    target_folder = create_template_folder(sample_service, name='target')
    f1 = create_template_folder(sample_service, name='f1')
    f2 = create_template_folder(sample_service, name='f2')

    t1 = create_template(sample_service, template_name='t1', folder=f1)
    t2 = create_template(sample_service, template_name='t2', folder=f1)
    t3 = create_template(sample_service, template_name='t3', folder=f2)
    t4 = create_template(sample_service, template_name='t4', folder=target_folder)

    admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={
            'templates': [str(t1.id)],
            'folders': [str(f1.id)]
        },
        _expected_status=204
    )

    assert target_folder.parent is None
    assert f1.parent == target_folder
    assert f2.parent is None  # unchanged

    assert t1.folder == target_folder  # moved out of f1, even though f1 is also being moved
    assert t2.folder == f1  # stays in f1, though f1 has moved
    assert t3.folder == f2  # unchanged
    assert t4.folder == target_folder  # unchanged

    # versions are all unchanged
    assert t1.version == 1
    assert t2.version == 1
    assert t3.version == 1
    assert t4.version == 1


def test_move_to_folder_moves_folders_and_templates_to_top_level_if_no_target(admin_request, sample_service):
    f1 = create_template_folder(sample_service, name='f1')
    f2 = create_template_folder(sample_service, name='f2', parent=f1)

    t1 = create_template(sample_service, template_name='t1', folder=f1)
    t2 = create_template(sample_service, template_name='t2', folder=f1)
    t3 = create_template(sample_service, template_name='t3', folder=f2)

    admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=sample_service.id,
        target_template_folder_id=None,
        _data={
            'templates': [str(t1.id)],
            'folders': [str(f2.id)]
        },
        _expected_status=204
    )

    assert f1.parent is None  # unchanged
    assert f2.parent is None

    assert t1.folder is None  # moved out of f1
    assert t2.folder == f1  # unchanged
    assert t3.folder == f2  # stayed in f2 even though the parent changed


def test_move_to_folder_rejects_folder_from_other_service(admin_request, notify_db_session):
    s1 = create_service(service_name='s1')
    s2 = create_service(service_name='s2')

    f2 = create_template_folder(s2)

    response = admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=s1.id,
        target_template_folder_id=None,
        _data={
            'templates': [],
            'folders': [str(f2.id)]
        },
        _expected_status=400
    )
    assert response['message'] == 'No folder found with id {} for service {}'.format(f2.id, s1.id)


def test_move_to_folder_rejects_template_from_other_service(admin_request, notify_db_session):
    s1 = create_service(service_name='s1')
    s2 = create_service(service_name='s2')

    t2 = create_template(s2)

    response = admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=s1.id,
        target_template_folder_id=None,
        _data={
            'templates': [str(t2.id)],
            'folders': []
        },
        _expected_status=400
    )
    assert response['message'] == 'Could not move to folder: No template found with id {} for service {}'.format(
        t2.id, s1.id
    )


def test_move_to_folder_rejects_if_it_would_cause_folder_loop(admin_request, sample_service):
    f1 = create_template_folder(sample_service, name='f1')
    target_folder = create_template_folder(sample_service, name='target', parent=f1)

    response = admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={
            'templates': [],
            'folders': [str(f1.id)]
        },
        _expected_status=400
    )
    assert response['message'] == 'Could not move to folder: {} is an ancestor of target folder {}'.format(
        f1.id, target_folder.id
    )


def test_move_to_folder_itself_is_rejected(admin_request, sample_service):
    target_folder = create_template_folder(sample_service, name='target')

    response = admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={
            'templates': [],
            'folders': [str(target_folder.id)]
        },
        _expected_status=400
    )
    response['message'] == 'Could not move to folder: {} to itself'.format(target_folder.id)


def test_move_to_folder_skips_archived_templates(admin_request, sample_service):
    target_folder = create_template_folder(sample_service)
    other_folder = create_template_folder(sample_service)

    archived_template = create_template(sample_service, archived=True, folder=None)
    unarchived_template = create_template(sample_service, archived=False, folder=other_folder)

    archived_timestamp = archived_template.updated_at

    admin_request.post(
        'template_folder.move_to_template_folder',
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={
            'templates': [str(archived_template.id), str(unarchived_template.id)],
            'folders': []
        },
        _expected_status=204
    )

    assert archived_template.updated_at == archived_timestamp
    assert archived_template.folder is None
    assert unarchived_template.folder == target_folder
