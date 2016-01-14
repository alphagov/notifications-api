import uuid
from app.dao.tokens_dao import (save_model_token, get_model_tokens, get_unsigned_token, _generate_token, _get_token)
from datetime import datetime
from app.models import Token
from pytest import fail
from sqlalchemy.orm.exc import NoResultFound


def test_token_is_signed_and_can_be_read_again(notify_api):
    import uuid
    with notify_api.test_request_context():
        token = str(uuid.uuid4())
        signed_token = _generate_token(token=token)
        assert token == _get_token(signed_token)
        assert signed_token != token


def test_save_token_should_create_new_token(notify_api, notify_db, notify_db_session, sample_service):
    api_token = Token(**{'service_id': sample_service.id})
    save_model_token(api_token)

    all_tokens = get_model_tokens()
    assert len(all_tokens) == 1
    assert all_tokens[0] == api_token


def test_save_token_should_update_the_token(notify_api, notify_db, notify_db_session, sample_token):
    now = datetime.utcnow()
    saved_token = get_model_tokens(sample_token.service_id)
    save_model_token(saved_token, update_dict={'id': saved_token.id, 'expiry_date': now})
    all_tokens = get_model_tokens()
    assert len(all_tokens) == 1
    assert all_tokens[0].expiry_date == now
    assert all_tokens[0].token == saved_token.token
    assert all_tokens[0].id == saved_token.id
    assert all_tokens[0].service_id == saved_token.service_id


def test_get_token_should_raise_exception_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                      sample_service):
    try:
        get_model_tokens(sample_service.id)
        fail("Should have thrown a NoResultFound exception")
    except NoResultFound:
        pass


def test_get_token_should_return_none_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                  sample_service):
    assert get_model_tokens(service_id=sample_service.id, raise_=False) is None


def test_should_return_token_for_service(notify_api, notify_db, notify_db_session, sample_token):
    token = get_model_tokens(sample_token.service_id)
    assert token == sample_token


def test_should_return_unsigned_token_for_service_id(notify_api, notify_db, notify_db_session,
                                                     sample_token):
    unsigned_token = get_unsigned_token(sample_token.service_id)
    assert sample_token.token != unsigned_token
    assert unsigned_token == _get_token(sample_token.token)
