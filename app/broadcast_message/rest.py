from datetime import datetime

import iso8601
from flask import Blueprint, jsonify, request, current_app
from app.config import QueueNames
from app.dao.templates_dao import dao_get_template_by_id_and_service_id
from app.dao.users_dao import get_user_by_id
from app.dao.broadcast_message_dao import (
    dao_create_broadcast_message,
    dao_get_broadcast_message_by_id_and_service_id,
    dao_get_broadcast_messages_for_service,
    dao_update_broadcast_message,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.errors import register_errors, InvalidRequest
from app.models import BroadcastMessage, BroadcastStatusType, BroadcastEvent, BroadcastEventMessageType
from app.celery.broadcast_message_tasks import send_broadcast_event
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


def _update_broadcast_message(broadcast_message, new_status, updating_user):
    if updating_user not in broadcast_message.service.users:
        raise InvalidRequest(
            f'User {updating_user.id} cannot approve broadcast_message {broadcast_message.id} from other service',
            status_code=400
        )

    if new_status not in BroadcastStatusType.ALLOWED_STATUS_TRANSITIONS[broadcast_message.status]:
        raise InvalidRequest(
            f'Cannot move broadcast_message {broadcast_message.id} from {broadcast_message.status} to {new_status}',
            status_code=400
        )

    if new_status == BroadcastStatusType.BROADCASTING:
        # TODO: Remove this platform admin shortcut when the feature goes live
        if updating_user == broadcast_message.created_by and not (
            # platform admins and trial mode services can approve their own broadcasts
            updating_user.platform_admin or
            broadcast_message.service.restricted
        ):
            raise InvalidRequest(
                f'User {updating_user.id} cannot approve their own broadcast_message {broadcast_message.id}',
                status_code=400
            )
        else:
            broadcast_message.approved_at = datetime.utcnow()
            broadcast_message.approved_by = updating_user

    if new_status == BroadcastStatusType.CANCELLED:
        broadcast_message.cancelled_at = datetime.utcnow()
        broadcast_message.cancelled_by = updating_user

    current_app.logger.info(
        f'broadcast_message {broadcast_message.id} moving from {broadcast_message.status} to {new_status}'
    )
    broadcast_message.status = new_status


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

    if broadcast_message.status not in BroadcastStatusType.PRE_BROADCAST_STATUSES:
        raise InvalidRequest(
            f'Cannot update broadcast_message {broadcast_message.id} while it has status {broadcast_message.status}',
            status_code=400
        )

    if 'personalisation' in data:
        broadcast_message.personalisation = data['personalisation']
    if 'starts_at' in data:
        broadcast_message.starts_at = _parse_nullable_datetime(data['starts_at'])
    if 'finishes_at' in data:
        broadcast_message.finishes_at = _parse_nullable_datetime(data['finishes_at'])
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
    updating_user = get_user_by_id(data['created_by'])

    _update_broadcast_message(broadcast_message, new_status, updating_user)
    dao_update_broadcast_message(broadcast_message)

    if new_status in {BroadcastStatusType.BROADCASTING, BroadcastStatusType.CANCELLED}:
        _create_broadcast_event(broadcast_message)

    return jsonify(broadcast_message.serialize()), 200


def _create_broadcast_event(broadcast_message):
    """
    Creates a broadcast event, stores it in the database, and triggers the task to send the CAP XML off
    """
    msg_types = {
        BroadcastStatusType.BROADCASTING: BroadcastEventMessageType.ALERT,
        BroadcastStatusType.CANCELLED: BroadcastEventMessageType.CANCEL,
    }

    if broadcast_message.status == BroadcastStatusType.CANCELLED:
        transmitted_finishes_at = broadcast_message.cancelled_at
    else:
        transmitted_finishes_at = broadcast_message.finishes_at

    # TODO: This doesn't support placeholders yet. We shouldn't use BroadcastMessageTemplate when we add placeholders
    # as that just outputs XML, we need the raw text.
    event = BroadcastEvent(
        service=broadcast_message.service,
        broadcast_message=broadcast_message,
        message_type=msg_types[broadcast_message.status],
        transmitted_content={"body": broadcast_message.template.content},
        transmitted_areas=broadcast_message.areas,
        # TODO: Probably move this somewhere more standalone too and imply that it shouldn't change. Should it include
        # a service based identifier too? eg "flood-warnings@notifications.service.gov.uk" or similar
        transmitted_sender='notifications.service.gov.uk',

        # TODO: Should this be set to now? Or the original starts_at?
        transmitted_starts_at=broadcast_message.starts_at,
        # TODO: When cancelling, do we need to set this to now? Or should we keep it as the original time.
        transmitted_finishes_at=transmitted_finishes_at,
    )

    # save to the DB
    dao_create_broadcast_message(event)

    send_broadcast_event.apply_async(
        kwargs={'broadcast_event_id': str(event.id)},
        queue=QueueNames.NOTIFY
    )
