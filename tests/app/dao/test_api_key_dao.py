from datetime import datetime

from pytest import fail
from sqlalchemy.orm.exc import NoResultFound

from app.dao.api_key_dao import (save_model_api_key,
                                 get_model_api_keys,
                                 get_unsigned_secrets,
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


def test_save_api_key_should_create_new_api_key_and_history(notify_api, notify_db, notify_db_session, sample_service):
    api_key = ApiKey(**{'service': sample_service,
                        'name': sample_service.name,
                        'created_by': sample_service.created_by})
    save_model_api_key(api_key)

    all_api_keys = get_model_api_keys(service_id=sample_service.id)
    assert len(all_api_keys) == 1
    assert all_api_keys[0] == api_key
    assert api_key.version == 1

    all_history = api_key.get_history_model().query.all()
    assert len(all_history) == 1
    assert all_history[0].id == api_key.id
    assert all_history[0].version == api_key.version


def test_expire_api_key_should_update_the_api_key_and_create_history_record(notify_api,
                                                                            notify_db,
                                                                            notify_db_session,
                                                                            sample_api_key):
    now = datetime.utcnow()
    saved_api_key = get_model_api_keys(service_id=sample_api_key.service_id, id=sample_api_key.id)
    save_model_api_key(saved_api_key, update_dict={'id': saved_api_key.id, 'expiry_date': now})
    all_api_keys = get_model_api_keys(service_id=sample_api_key.service_id)
    assert len(all_api_keys) == 1
    assert all_api_keys[0].expiry_date == now
    assert all_api_keys[0].secret == saved_api_key.secret
    assert all_api_keys[0].id == saved_api_key.id
    assert all_api_keys[0].service_id == saved_api_key.service_id

    all_history = saved_api_key.get_history_model().query.all()
    assert len(all_history) == 2
    assert all_history[0].id == saved_api_key.id
    assert all_history[1].id == saved_api_key.id
    sorted_all_history = sorted(all_history, key=lambda hist: hist.version)
    sorted_all_history[0].version = 1
    sorted_all_history[1].version = 2


def test_get_api_key_should_raise_exception_when_api_key_does_not_exist(notify_api,
                                                                        notify_db,
                                                                        notify_db_session,
                                                                        sample_service,
                                                                        fake_uuid):
    try:
        get_model_api_keys(sample_service.id, id=fake_uuid)
        fail("Should have thrown a NoResultFound exception")
    except NoResultFound:
        pass


def test_should_return_api_key_for_service(notify_api, notify_db, notify_db_session, sample_api_key):
    api_key = get_model_api_keys(service_id=sample_api_key.service_id, id=sample_api_key.id)
    assert api_key == sample_api_key


def test_should_return_unsigned_api_keys_for_service_id(notify_api,
                                                        notify_db,
                                                        notify_db_session,
                                                        sample_api_key):
    unsigned_api_key = get_unsigned_secrets(sample_api_key.service_id)
    assert len(unsigned_api_key) == 1
    assert sample_api_key.secret != unsigned_api_key[0]
    assert unsigned_api_key[0] == _get_secret(sample_api_key.secret)


def test_get_unsigned_secret_returns_key(notify_api,
                                         notify_db,
                                         notify_db_session,
                                         sample_api_key):
    unsigned_api_key = get_unsigned_secret(sample_api_key.id)
    assert sample_api_key.secret != unsigned_api_key
    assert unsigned_api_key == _get_secret(sample_api_key.secret)


def test_should_not_allow_duplicate_key_names_per_service(notify_api,
                                                          notify_db,
                                                          notify_db_session,
                                                          sample_api_key,
                                                          fake_uuid):
    api_key = ApiKey(**{'id': fake_uuid,
                        'service': sample_api_key.service,
                        'name': sample_api_key.name,
                        'created_by': sample_api_key.created_by})
    try:
        save_model_api_key(api_key)
        fail("should throw IntegrityError")
    except:
        pass
