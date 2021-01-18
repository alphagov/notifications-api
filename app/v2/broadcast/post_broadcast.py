from itertools import chain
from flask import jsonify, request
from app import authenticated_service, api_user
from app.broadcast_message.translators import cap_xml_to_dict
from app.dao.dao_utils import dao_save_object
from app.notifications.validators import check_service_has_permission
from app.models import BROADCAST_TYPE, BroadcastMessage, BroadcastStatusType
from app.schema_validation import validate
from app.v2.broadcast import v2_broadcast_blueprint
from app.v2.broadcast.broadcast_schemas import post_broadcast_schema


@v2_broadcast_blueprint.route("", methods=['POST'])
def create_broadcast():

    check_service_has_permission(
        BROADCAST_TYPE,
        authenticated_service.permissions,
    )

    if request.content_type == 'application/json':
        broadcast_json = request.get_json()
    elif request.content_type == 'application/cap+xml':
        broadcast_json = cap_xml_to_dict(request.get_data(as_text=True))
    else:
        raise BadRequestError(
            message=f'Content type {request.content_type} not supported',
            status_code=400,
        )

    validate(broadcast_json, post_broadcast_schema)

    broadcast_message = BroadcastMessage(
        service_id=authenticated_service.id,
        content=broadcast_json['content'],
        reference=broadcast_json['reference'],
        areas={
            'areas': [
                area['name'] for area in broadcast_json['areas']
            ],
            'simple_polygons': list(chain.from_iterable((
                area['polygons'] for area in broadcast_json['areas']
            )))
        },
        status=BroadcastStatusType.PENDING_APPROVAL,
        api_key_id=api_user.id,
        # The client may pass in broadcast_json['expires'] but it’s
        # simpler for now to ignore it and have the rules around expiry
        # for broadcasts created with the API match those created from
        # the admin app
    )

    dao_save_object(broadcast_message)

    return jsonify(broadcast_message.serialize()), 201
