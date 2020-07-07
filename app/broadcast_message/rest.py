from datetime import datetime

import iso8601
from flask import Blueprint, jsonify, request

from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.dao.users_dao import get_user_by_id
from app.dao.broadcast_message_dao import (
    dao_create_broadcast_message,
    dao_get_broadcast_message_by_id_and_service_id,
    dao_get_broadcast_messages_for_service,
    dao_update_broadcast_message,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import register_errors
from app.models import BroadcastMessage, BroadcastStatusType
from app.broadcast_message.broadcast_message_schema import (
    create_broadcast_message_schema,
    update_broadcast_message_schema,
    update_broadcast_message_status_schema,
)
from app.schema_validation import validate

broadcast_message_blueprint = Blueprint(
    'broadcast_message',
    __name__,
    url_prefix='/service/<uuid:service_id>/broadcast-message'
)
register_errors(broadcast_message_blueprint)


def _parse_nullable_datetime(dt):
    if dt:
        return iso8601.parse_date(dt).replace(tzinfo=None)
    return dt


@broadcast_message_blueprint.route('', methods=['GET'])
def get_broadcast_messages_for_service(service_id):
    # TODO: should this return template content/data in some way? or can we rely on them being cached admin side.
    # we might need stuff like template name for showing on the dashboard.
    # TODO: should this paginate or filter on dates or anything?
    broadcast_messages = [o.serialize() for o in dao_get_broadcast_messages_for_service(service_id)]
    return jsonify(broadcast_messages=broadcast_messages)


@broadcast_message_blueprint.route('/<uuid:broadcast_message_id>', methods=['GET'])
def get_broadcast_message(service_id, broadcast_message_id):
    return jsonify(dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id).serialize())


@broadcast_message_blueprint.route('', methods=['POST'])
def create_broadcast_message(service_id):
    data = request.get_json()

    validate(data, create_broadcast_message_schema)
    service = dao_fetch_service_by_id(data['service_id'])
    user = get_user_by_id(data['created_by'])
    template = dao_get_template_by_id_and_service_id(data['template_id'], data['service_id'])

    broadcast_message = BroadcastMessage(
        service_id=service.id,
        template_id=template.id,
        template_version=template.version,
        personalisation=data.get('personalisation', {}),
        areas=data.get('areas', []),
        status=BroadcastStatusType.DRAFT,
        starts_at=_parse_nullable_datetime(data.get('starts_at')),
        finishes_at=_parse_nullable_datetime(data.get('finishes_at')),
        created_by_id=user.id,
    )

    dao_create_broadcast_message(broadcast_message)

    return jsonify(broadcast_message.serialize()), 201


@broadcast_message_blueprint.route('/<uuid:broadcast_message_id>', methods=['POST'])
def update_broadcast_message(service_id, broadcast_message_id):
    data = request.get_json()

    validate(data, update_broadcast_message_schema)

    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id)

    if 'personalisation' in data:
        broadcast_message.personalisation = data['personalisation']
    if 'starts_at' in data:
        broadcast_message.starts_at = _parse_nullable_datetime(data['starts_at'])
    if 'finishes_at' in data:
        broadcast_message.starts_at = _parse_nullable_datetime(data['finishes_at'])
    if 'areas' in data:
        broadcast_message.areas = data['areas']

    dao_update_broadcast_message(broadcast_message)

    return jsonify(broadcast_message.serialize()), 200


@broadcast_message_blueprint.route('/<uuid:broadcast_message_id>/status', methods=['POST'])
def update_broadcast_message_status(service_id, broadcast_message_id):
    data = request.get_json()

    validate(data, update_broadcast_message_status_schema)
    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(broadcast_message_id, service_id)

    new_status = data['status']

    # TODO: Restrict status transitions
    # TODO: Do we need to validate that the user belongs to the same service, isn't the creator, has permissions, etc?
    # or is that admin's job
    if new_status == BroadcastStatusType.BROADCASTING:
        broadcast_message.approved_at = datetime.utcnow()
        broadcast_message.approved_by = get_user_by_id(data['created_by'])
    if new_status == BroadcastStatusType.CANCELLED:
        broadcast_message.cancelled_at = datetime.utcnow()
        broadcast_message.cancelled_by = get_user_by_id(data['created_by'])

    broadcast_message.status = new_status

    dao_update_broadcast_message(broadcast_message)

    return jsonify(broadcast_message.serialize()), 200
