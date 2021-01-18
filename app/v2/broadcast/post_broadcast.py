from flask import jsonify, request
from app import authenticated_service, api_user
from app.dao.dao_utils import dao_save_object
from app.notifications.validators import check_service_has_permission
from app.models import BROADCAST_TYPE, BroadcastMessage, BroadcastStatusType
from app.v2.broadcast import v2_broadcast_blueprint


@v2_broadcast_blueprint.route("", methods=['POST'])
def create_broadcast():

    check_service_has_permission(
        BROADCAST_TYPE,
        authenticated_service.permissions,
    )

    request_json = request.get_json()

    broadcast_message = BroadcastMessage(
        service_id=authenticated_service.id,
        content=request_json['content'],
        reference=request_json['reference'],
        areas={
            "areas": [],
            "simple_polygons": request_json['polygons'],
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
