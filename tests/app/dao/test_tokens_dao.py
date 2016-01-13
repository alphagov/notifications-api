import uuid
from app.dao import tokens_dao
from datetime import datetime

from app.models import Token
from pytest import fail
from sqlalchemy.orm.exc import NoResultFound


def test_save_token_should_create_new_token(notify_api, notify_db, notify_db_session, sample_service):
    token = uuid.uuid4()
    api_token = Token(**{'token': token, 'service_id': sample_service.id})

    tokens_dao.save_token_model(api_token)

    all_tokens = tokens_dao.get_model_tokens()
    assert len(all_tokens) == 1
    assert all_tokens[0].token == str(token)


def test_save_token_should_update_the_token(notify_api, notify_db, notify_db_session, sample_service):
    api_token = Token(**{'token': uuid.uuid4(), 'service_id': sample_service.id})
    tokens_dao.save_token_model(api_token)
    now = datetime.utcnow()
    saved_token = tokens_dao.get_model_tokens(sample_service.id)
    tokens_dao.save_token_model(saved_token, update_dict={'id': saved_token.id, 'expiry_date': now})
    all_tokens = tokens_dao.get_model_tokens()
    assert len(all_tokens) == 1
    assert all_tokens[0].expiry_date == now


def test_get_token_should_raise_exception_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                      sample_service):
    try:
        tokens_dao.get_model_tokens(sample_service.id)
        fail()
    except NoResultFound:
        pass


def test_get_token_should_return_none_when_service_does_not_exist(notify_api, notify_db, notify_db_session,
                                                                  sample_service):
    assert tokens_dao.get_model_tokens(service_id=sample_service.id, raise_=False) is None


def test_should_return_token_for_service(notify_api, notify_db, notify_db_session, sample_service):
    the_token = str(uuid.uuid4())
    api_token = Token(**{'token': the_token, 'service_id': sample_service.id})
    tokens_dao.save_token_model(api_token)
    token = tokens_dao.get_model_tokens(sample_service.id)
    assert token.service_id == sample_service.id
    assert token.token == str(the_token)
