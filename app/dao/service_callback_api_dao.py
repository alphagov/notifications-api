from datetime import datetime

from app import db, create_uuid
from app.dao.dao_utils import transactional, version_class
from app.models import ServiceCallbackApi

from app.models import DELIVERY_STATUS_CALLBACK_TYPE


@transactional
@version_class(ServiceCallbackApi)
def save_service_callback_api(service_callback_api):
    service_callback_api.id = create_uuid()
    service_callback_api.created_at = datetime.utcnow()
    db.session.add(service_callback_api)


@transactional
@version_class(ServiceCallbackApi)
def reset_service_callback_api(service_callback_api, updated_by_id, url=None, bearer_token=None):
    if url:
        service_callback_api.url = url
    if bearer_token:
        service_callback_api.bearer_token = bearer_token
    service_callback_api.updated_by_id = updated_by_id
    service_callback_api.updated_at = datetime.utcnow()

    db.session.add(service_callback_api)


def get_service_callback_api(service_callback_api_id, service_id):
    return ServiceCallbackApi.query.filter_by(id=service_callback_api_id, service_id=service_id).first()


def get_service_delivery_status_callback_api_for_service(service_id):
    return ServiceCallbackApi.query.filter_by(
        service_id=service_id,
        callback_type=DELIVERY_STATUS_CALLBACK_TYPE
    ).first()


@transactional
def delete_service_callback_api(service_callback_api):
    db.session.delete(service_callback_api)
