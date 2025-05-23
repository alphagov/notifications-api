from datetime import datetime

from app import db
from app.constants import ServiceCallbackTypes
from app.dao.dao_utils import autocommit, version_class
from app.models import ServiceCallbackApi


@autocommit
@version_class(ServiceCallbackApi)
def save_service_callback_api(service_callback_api):
    service_callback_api.created_at = datetime.utcnow()
    db.session.add(service_callback_api)


@autocommit
@version_class(ServiceCallbackApi)
def reset_service_callback_api(service_callback_api, updated_by_id, url=None, bearer_token=None):
    if url:
        service_callback_api.url = url
    if bearer_token:
        service_callback_api.bearer_token = bearer_token
    service_callback_api.updated_by_id = updated_by_id
    service_callback_api.updated_at = datetime.utcnow()

    db.session.add(service_callback_api)


def get_service_callback_api(service_callback_api_id, service_id, callback_type):
    return ServiceCallbackApi.query.filter_by(
        id=service_callback_api_id, service_id=service_id, callback_type=callback_type
    ).first()


def get_service_callback_api_by_callback_type(service_id, callback_type):
    return ServiceCallbackApi.query.filter_by(service_id=service_id, callback_type=callback_type).first()


def get_delivery_status_callback_api_for_service(service_id):
    return ServiceCallbackApi.query.filter_by(
        service_id=service_id, callback_type=ServiceCallbackTypes.delivery_status.value
    ).first()


def get_returned_letter_callback_api_for_service(service_id):
    return ServiceCallbackApi.query.filter_by(
        service_id=service_id, callback_type=ServiceCallbackTypes.returned_letter.value
    ).first()


def get_complaint_callback_api_for_service(service_id):
    return ServiceCallbackApi.query.filter_by(
        service_id=service_id, callback_type=ServiceCallbackTypes.complaint.value
    ).first()


@autocommit
def delete_service_callback_api(service_callback_api):
    db.session.delete(service_callback_api)
