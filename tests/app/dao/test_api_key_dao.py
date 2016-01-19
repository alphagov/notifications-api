from datetime import datetime

from pytest import fail
from sqlalchemy.orm.exc import NoResultFound

from app.dao.api_key_dao import (save_model_api_key,
                                 get_model_api_keys,
                                 get_unsigned_secret,
                                 _generate_secret,
                                 _get_secret)
from app.models import ApiKey


def test_secret_is_signed_and_can_be_read_again(notify_api):
    import uuid
    with notify_api.test_request_context():
        token = str(uuid.uuid4())
        signed_secret = _generate_secret(token=token)
        assert token == _get_secret(signed_secret)
        assert signed_secret != token


def test_save_api_key_should_create_new_api_key(notify_api, notify_db, notify_db_session, sample_service):
    api_key = ApiKey(**{'service_id': sample_service.id, 'name': sample_service.name})
    save_model_api_key(api_key)

    all_api_keys = get_model_api_keys()
    assert len(all_api_keys) == 1
    assert all_api_keys[0] == api_key


def test_save_api_key_should_update_the_api_key(notify_api, notify_db, notify_db_session, sample_api_key):
    now = datetime.utcnow()
    saved_api_key = get_model_api_keys(sample_api_key.service_id)
    save_model_api_key(saved_api_key, update_dict={'id': saved_api_key.id, 'expiry_date': now})
    all_api_keys = get_model_api_keys()
    assert len(all_api_keys) == 1
    assert all_api_keys[0].expiry_date == now
    assert all_api_keys[0].secret == saved_api_key.secret
    assert all_api_keys[0].id == saved_api_key.id
    assert all_api_keys[0].service_id == saved_api_key.service_id


def test_get_api_key_should_raise_exception_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                        sample_service):
    try:
        get_model_api_keys(sample_service.id)
        fail("Should have thrown a NoResultFound exception")
    except NoResultFound:
        pass


def test_get_api_key_should_return_none_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                    sample_service):
    assert get_model_api_keys(service_id=sample_service.id, raise_=False) is None


def test_should_return_api_key_for_service(notify_api, notify_db, notify_db_session, sample_api_key):
    api_key = get_model_api_keys(sample_api_key.service_id)
    assert api_key == sample_api_key


def test_should_return_unsigned_api_key_for_service_id(notify_api,
                                                       notify_db,
                                                       notify_db_session,
                                                       sample_api_key):
    unsigned_api_key = get_unsigned_secret(sample_api_key.service_id)
    assert sample_api_key.secret != unsigned_api_key
    assert unsigned_api_key == _get_secret(sample_api_key.secret)
