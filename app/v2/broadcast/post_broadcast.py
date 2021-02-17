from itertools import chain
from flask import current_app, jsonify, request
from notifications_utils.polygons import Polygons
from notifications_utils.template import BroadcastMessageTemplate
from app import authenticated_service, api_user
from app.broadcast_message.translators import cap_xml_to_dict
from app.dao.dao_utils import dao_save_object
from app.notifications.validators import check_service_has_permission
from app.models import BROADCAST_TYPE, BroadcastMessage, BroadcastStatusType
from app.schema_validation import validate
from app.v2.broadcast import v2_broadcast_blueprint
from app.v2.broadcast.broadcast_schemas import post_broadcast_schema
from app.v2.errors import BadRequestError, ValidationError
from app.xml_schemas import validate_xml


@v2_broadcast_blueprint.route("", methods=['POST'])
def create_broadcast():

    check_service_has_permission(
        BROADCAST_TYPE,
        authenticated_service.permissions,
    )

    if request.content_type != 'application/cap+xml':
        raise BadRequestError(
            message=f'Content type {request.content_type} not supported',
            status_code=415,
        )

    cap_xml = request.get_data()

    if not validate_xml(cap_xml, 'CAP-v1.2.xsd'):
        raise BadRequestError(
            message='Request data is not valid CAP XML',
            status_code=400,
        )

    broadcast_json = cap_xml_to_dict(cap_xml)

    validate(broadcast_json, post_broadcast_schema)

    polygons = Polygons(list(chain.from_iterable((
        area['polygons'] for area in broadcast_json['areas']
    ))))

    template = BroadcastMessageTemplate.from_content(
        broadcast_json['content']
    )

    if template.content_too_long:
        raise ValidationError(
            message=(
                f'description must be {template.max_content_count:,.0f} '
                f'characters or fewer'
            ) + (
                ' (because it could not be GSM7 encoded)'
                if template.non_gsm_characters else ''
            ),
            status_code=400,
        )

    broadcast_message = BroadcastMessage(
        service_id=authenticated_service.id,
        content=broadcast_json['content'],
        reference=broadcast_json['reference'],
        areas={
            'areas': [
                area['name'] for area in broadcast_json['areas']
            ],
            'simple_polygons': polygons.smooth.simplify.as_coordinate_pairs_long_lat,
        },
        status=BroadcastStatusType.PENDING_APPROVAL,
        api_key_id=api_user.id,
        stubbed=authenticated_service.restricted
        # The client may pass in broadcast_json['expires'] but it’s
        # simpler for now to ignore it and have the rules around expiry
        # for broadcasts created with the API match those created from
        # the admin app
    )

    dao_save_object(broadcast_message)

    current_app.logger.info(
        f'Broadcast message {broadcast_message.id} created for service '
        f'{authenticated_service.id} with reference {broadcast_json["reference"]}'
    )

    return jsonify(broadcast_message.serialize()), 201
