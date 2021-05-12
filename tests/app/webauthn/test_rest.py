import uuid
from unittest.mock import ANY

import pytest

from tests.app.db import create_user, create_webauthn_credential


def test_get_webauthn_credentials_returns_all_credentials_for_user(admin_request, notify_db_session):
    me = create_user(email='a')
    other = create_user(email='b')
    first = create_webauthn_credential(me, '1')
    create_webauthn_credential(me, '2')
    create_webauthn_credential(other, '3')

    response = admin_request.get(
        'webauthn.get_webauthn_credentials',
        user_id=me.id,
    )

    creds = sorted(response['data'], key=lambda x: x['name'])
    assert len(creds) == 2

    assert creds[0] == {
        'id': str(first.id),
        'user_id': str(me.id),
        'name': '1',
        'credential_data': 'ABC123',
        'created_at': ANY,
        'updated_at': None
    }

    assert creds[1]['name'] == '2'


def test_get_webauthn_credentials_returns_empty_list_if_no_creds(admin_request, sample_user):
    response = admin_request.get('webauthn.get_webauthn_credentials', user_id=sample_user.id)
    assert response == {'data': []}


def test_get_webauthn_credentials_errors_if_user_doesnt_exist(admin_request, sample_user):
    create_webauthn_credential(sample_user, '1')

    admin_request.get(
        'webauthn.get_webauthn_credentials',
        user_id=uuid.uuid4(),
        _expected_status=404
    )


def test_create_webauthn_credential_returns_201(admin_request, sample_user):
    response = admin_request.post(
        'webauthn.create_webauthn_credential',
        user_id=sample_user.id,
        _data={
            'name': 'my key',
            'credential_data': 'ABC123',
            'registration_response': 'DEF456',
        },
        _expected_status=201
    )
    assert len(sample_user.webauthn_credentials) == 1

    new_cred = sample_user.webauthn_credentials[0]

    assert new_cred.name == 'my key'
    assert new_cred.credential_data == 'ABC123'
    assert new_cred.registration_response == 'DEF456'
    assert response['data']['id'] == str(new_cred.id)


@pytest.mark.parametrize('data, err_msg', [
    # missing registration_response
    (
        {'name': 'my key', 'credential_data': 'ABC123'},
        'registration_response is a required property'
    ),
    # name is null
    (
        {'name': None, 'credential_data': 'ABC123'},
        'name None is not of type string'
    ),
    # name is empty
    (
        {'name': '', 'credential_data': 'ABC123'},
        'name  is too short'
    ),
])
def test_create_webauthn_credential_errors_if_schema_violation(admin_request, sample_user, data, err_msg):
    response = admin_request.post(
        'webauthn.create_webauthn_credential',
        user_id=sample_user.id,
        _data=data,
        _expected_status=400
    )
    assert response['errors'][0] == {
        'error': 'ValidationError',
        'message': err_msg
    }


def test_update_webauthn_credential_returns_200(admin_request, sample_user):
    cred = create_webauthn_credential(sample_user)
    assert cred.name != 'new name'

    response = admin_request.post(
        'webauthn.update_webauthn_credential',
        user_id=sample_user.id,
        webauthn_credential_id=cred.id,
        _data={
            'name': 'new name',
        },
    )
    assert response['data']['id'] == str(cred.id)
    assert response['data']['name'] == 'new name'


@pytest.mark.parametrize('data, err_msg', [
    # you can't update credential_data
    (
        {'name': 'my key', 'credential_data': 'NAUGHTY123'},
        'Additional properties are not allowed (credential_data was unexpected)'
    ),
    # name is null
    (
        {'name': None},
        'name None is not of type string'
    ),
    # name is empty
    (
        {'name': ''},
        'name  is too short'
    ),
])
def test_update_webauthn_credential_errors_if_schema_violation(admin_request, sample_user, data, err_msg):
    cred = create_webauthn_credential(sample_user)
    response = admin_request.post(
        'webauthn.update_webauthn_credential',
        user_id=sample_user.id,
        webauthn_credential_id=cred.id,
        _data=data,
        _expected_status=400
    )
    assert response['errors'][0] == {
        'error': 'ValidationError',
        'message': err_msg
    }


def test_update_webauthn_credential_errors_if_webauthn_credential_doesnt_exist(admin_request, sample_user):
    admin_request.post(
        'webauthn.update_webauthn_credential',
        user_id=sample_user.id,
        webauthn_credential_id=uuid.uuid4(),
        _data={
            'name': 'my key',
        },
        _expected_status=404
    )


def test_update_webauthn_credential_errors_if_user_id_doesnt_match(admin_request, notify_db_session):
    user_1 = create_user(email='1')
    user_2 = create_user(email='2')
    cred_2 = create_webauthn_credential(user_2)

    response = admin_request.post(
        'webauthn.update_webauthn_credential',
        user_id=user_1.id,
        webauthn_credential_id=cred_2.id,
        _data={
            'name': 'new key name',
        },
        _expected_status=404
    )

    assert response['message'] == 'No result found'


def test_delete_webauthn_credential_returns_204(admin_request, sample_user):
    cred1 = create_webauthn_credential(sample_user)
    cred2 = create_webauthn_credential(sample_user)
    admin_request.delete(
        'webauthn.update_webauthn_credential',
        user_id=sample_user.id,
        webauthn_credential_id=cred1.id,
        _expected_status=204
    )
    assert sample_user.webauthn_credentials == [cred2]


def test_delete_webauthn_credential_errors_if_last_key(admin_request, sample_user):
    cred = create_webauthn_credential(sample_user)
    response = admin_request.delete(
        'webauthn.delete_webauthn_credential',
        user_id=sample_user.id,
        webauthn_credential_id=cred.id,
        _expected_status=400
    )
    assert response['message'] == 'Cannot delete last remaining webauthn credential for user'


def test_delete_webauthn_credential_errors_if_user_id_doesnt_match(admin_request, notify_db_session):
    user_1 = create_user(email='1')
    user_2 = create_user(email='2')
    cred_2a = create_webauthn_credential(user_2)

    response = admin_request.delete(
        'webauthn.delete_webauthn_credential',
        user_id=user_1.id,
        webauthn_credential_id=cred_2a.id,
        _expected_status=404
    )

    assert response['message'] == 'No result found'
