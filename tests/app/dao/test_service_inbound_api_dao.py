import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.authentication.utils import get_secret
from app.dao.service_inbound_api_dao import save_service_inbound_api, reset_service_inbound_api, \
    get_service_inbound_api
from app.models import ServiceInboundApi


def test_save_service_inbound_api(sample_service):
    service_inbound_api = ServiceInboundApi(
        service_id=sample_service.id,
        url="https::/some_service/inbound_messages",
        bearer_token="some_unique_string",
        updated_by_id=sample_service.users[0].id
    )

    save_service_inbound_api(service_inbound_api)

    results = ServiceInboundApi.query.all()
    assert len(results) == 1
    inbound_api = results[0]
    assert inbound_api.id
    assert inbound_api.service_id == sample_service.id
    assert inbound_api.updated_by_id == sample_service.users[0].id
    assert inbound_api.url == "https::/some_service/inbound_messages"
    assert inbound_api.unsigned_bearer_token == "some_unique_string"
    assert inbound_api.bearer_token != "some_unique_string"
    assert not inbound_api.updated_at

    versioned = ServiceInboundApi.get_history_model().query.filter_by(id=inbound_api.id).one()
    assert versioned.id == inbound_api.id
    assert versioned.service_id == sample_service.id
    assert versioned.updated_by_id == sample_service.users[0].id
    assert versioned.url == "https::/some_service/inbound_messages"
    assert versioned.bearer_token != "some_unique_string"
    assert not versioned.updated_at
    assert versioned.version == 1


def test_save_service_inbound_api_fails_if_service_does_not_exist(notify_db, notify_db_session):
    service_inbound_api = ServiceInboundApi(
        service_id=uuid.uuid4(),
        url="https::/some_service/inbound_messages",
        bearer_token="some_unique_string",
        updated_by_id=uuid.uuid4()
    )

    with pytest.raises(SQLAlchemyError):
        save_service_inbound_api(service_inbound_api)


def test_update_service_inbound_api(sample_service):
    service_inbound_api = ServiceInboundApi(
        service_id=sample_service.id,
        url="https::/some_service/inbound_messages",
        bearer_token="some_unique_string",
        updated_by_id=sample_service.users[0].id
    )

    save_service_inbound_api(service_inbound_api)
    results = ServiceInboundApi.query.all()
    assert len(results) == 1
    saved_inbound_api = results[0]

    updated_inbound_api = saved_inbound_api
    updated_inbound_api.url = "https::/some_service/changed_url"

    reset_service_inbound_api(updated_inbound_api)
    updated_results = ServiceInboundApi.query.all()
    assert len(updated_results) == 1
    updated = updated_results[0]
    assert updated.id
    assert updated.service_id == sample_service.id
    assert updated.updated_by_id == sample_service.users[0].id
    assert updated.url == "https::/some_service/changed_url"
    assert updated.unsigned_bearer_token == "some_unique_string"
    assert updated.bearer_token != "some_unique_string"
    assert updated.updated_at

    versioned_results = ServiceInboundApi.get_history_model().query.filter_by(id=saved_inbound_api.id).all()
    assert len(versioned_results) == 2
    for x in versioned_results:
        if x.version == 1:
            assert x.url == "https::/some_service/inbound_messages"
            assert not x.updated_at
        elif x.version == 2:
            assert x.url == "https::/some_service/changed_url"
            assert x.updated_at
        else:
            pytest.fail("version should not exist")
        assert x.id
        assert x.service_id == sample_service.id
        assert x.updated_by_id == sample_service.users[0].id
        assert get_secret(x.bearer_token) == "some_unique_string"


def test_get_service_inbound_api(sample_service):
    service_inbound_api = ServiceInboundApi(
        service_id=sample_service.id,
        url="https::/some_service/inbound_messages",
        bearer_token="some_unique_string",
        updated_by_id=sample_service.users[0].id
    )
    save_service_inbound_api(service_inbound_api)

    inbound_api = get_service_inbound_api(service_inbound_api.id, sample_service.id)
    assert inbound_api.id
    assert inbound_api.service_id == sample_service.id
    assert inbound_api.updated_by_id == sample_service.users[0].id
    assert inbound_api.url == "https::/some_service/inbound_messages"
    assert inbound_api.unsigned_bearer_token == "some_unique_string"
    assert inbound_api.bearer_token != "some_unique_string"
    assert not inbound_api.updated_at
