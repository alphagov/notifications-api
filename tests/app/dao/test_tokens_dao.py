import uuid
from app.dao import tokens_dao

from app.models import Token


def test_should_create_token(notify_api, notify_db, notify_db_session, sample_service):
    token = uuid.uuid4()
    api_token = Token(**{'token': token, 'service_id': sample_service.id})

    tokens_dao.save_token_model(api_token)

    all_tokens = tokens_dao.get_model_tokens()
    assert len(all_tokens) == 1
    assert all_tokens[0].token == str(token)


def test_should_delete_api_token(notify_api, notify_db, notify_db_session, sample_service):
    token = uuid.uuid4()
    api_token = Token(**{'token': token, 'service_id': sample_service.id})
    tokens_dao.save_token_model(api_token)
    all_tokens = tokens_dao.get_model_tokens()
    assert len(all_tokens) == 1

    tokens_dao.delete_model_token(all_tokens[0])
    empty_token_list = tokens_dao.get_model_tokens()
    assert len(empty_token_list) == 0


def test_should_return_token_for_service(notify_api, notify_db, notify_db_session, sample_service):
    the_token = str(uuid.uuid4())
    api_token = Token(**{'token': the_token, 'service_id': sample_service.id})
    tokens_dao.save_token_model(api_token)
    token = tokens_dao.get_model_tokens(sample_service.id)
    assert token.service_id == sample_service.id
    assert token.token == str(the_token)


def test_delete_model_token_should_remove_token(notify_api, notify_db, notify_db_session, sample_service):
    api_token = Token(**{'token': str(uuid.uuid4()), 'service_id': sample_service.id})
    tokens_dao.save_token_model(api_token)
    all_tokens = tokens_dao.get_model_tokens()
    assert len(all_tokens) == 1
    tokens_dao.delete_model_token(all_tokens[0])
    assert len(tokens_dao.get_model_tokens()) == 0
