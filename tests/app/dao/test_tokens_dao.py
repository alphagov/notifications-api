import uuid

from app.dao import api_tokens_dao
from app.models import ApiToken


def test_should_create_token(notify_api, notify_db, notify_db_session, sample_service):
    token = uuid.uuid4()
    api_token = ApiToken(**{'token': token, 'service_id': sample_service.id})

    api_tokens_dao.save_token_model(api_token)

    all_tokens = api_tokens_dao.get_model_api_tokens()

    assert len(all_tokens) == 1
    assert all_tokens[0].token == str(token)
