from datetime import datetime

from app import db, create_uuid
from app.authentication.utils import generate_secret
from app.dao.dao_utils import transactional, version_class
from app.models import ServiceInboundApi


@transactional
@version_class(ServiceInboundApi)
def save_service_inbound_api(service_inbound_api):
    service_inbound_api.id = create_uuid()
    service_inbound_api.created_at == datetime.utcnow()
    service_inbound_api.bearer_token = generate_secret(service_inbound_api.bearer_token)
    db.session.add(service_inbound_api)


@transactional
@version_class(ServiceInboundApi)
def reset_service_inbound_api(service_inbound_api, updated_by_id, url=None, bearer_token=None):
    if url:
        service_inbound_api.url = url
    if bearer_token:
        service_inbound_api.bearer_token = generate_secret(bearer_token)
    service_inbound_api.updated_by_id = updated_by_id
    service_inbound_api.updated_at = datetime.utcnow()

    db.session.add(service_inbound_api)


def get_service_inbound_api(service_inbound_api_id, service_id):
    return ServiceInboundApi.query.filter_by(id=service_inbound_api_id,
                                             service_id=service_id).first()
