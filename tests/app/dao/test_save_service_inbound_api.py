from app.dao.service_inbound_api_dao import save_service_inbound_api
from app.models import ServiceInboundApi


def test_save_service_inbound_api(sample_service):
    service_inbound_api = ServiceInboundApi(
        service_id=sample_service.id,
        url="https::/some_service/inbound_messages",
        bearer_token="some_unique_string"
    )

    save_service_inbound_api(service_inbound_api)

    results = ServiceInboundApi.query.all()
    assert len(results) == 1
    assert results[0].id
    assert results[0].service_id == sample_service.id
    assert results[0].url == "https::/some_service/inbound_messages"
    assert results[0].unsigned_bearer_token == "some_unique_string"
    assert results[0].bearer_token != "some_unique_string"
