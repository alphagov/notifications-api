from flask import jsonify, request, url_for, current_app

from notifications_utils.recipients import validate_and_format_phone_number
from notifications_utils.recipients import InvalidPhoneError

from app import authenticated_service
from app.dao import inbound_sms_dao
from app.schema_validation import validate
from app.v2.errors import BadRequestError
from app.v2.inbound_sms import v2_inbound_sms_blueprint
from app.v2.inbound_sms.inbound_sms_schemas import get_inbound_sms_request


@v2_inbound_sms_blueprint.route("", methods=['GET'])
def get_inbound_sms():
    data = validate(request.args.to_dict(), get_inbound_sms_request)

    if data.get('user_number'):
        try:
            data['user_number'] = validate_and_format_phone_number(data.get('user_number'))
        except InvalidPhoneError as e:
            raise BadRequestError(message=str(e))

    user_number = data.get('user_number', None)
    older_than = data.get('older_than', None)

    paginated_inbound_sms = inbound_sms_dao.dao_get_paginated_inbound_sms_for_service(
        authenticated_service.id,
        user_number=user_number,
        older_than=older_than,
        page_size=current_app.config.get('API_PAGE_SIZE')
    )

    return jsonify(
        received_text_messages=[i.serialize() for i in paginated_inbound_sms],
        links=_build_links(
            paginated_inbound_sms,
            user_number=user_number)
    ), 200


def _build_links(inbound_sms_list, user_number=None):
    _links = {
        'current': url_for(
            "v2_inbound_sms.get_inbound_sms",
            user_number=user_number,
            _external=True,
        ),
    }

    if inbound_sms_list:
        _links['next'] = url_for(
            "v2_inbound_sms.get_inbound_sms",
            user_number=user_number,
            older_than=inbound_sms_list[-1].id,
            _external=True,
        )

    return _links
