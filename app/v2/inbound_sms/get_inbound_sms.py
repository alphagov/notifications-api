import uuid

from flask import jsonify, request, url_for, current_app
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import abort

from notifications_utils.recipients import validate_and_format_phone_number
from notifications_utils.recipients import InvalidPhoneError

from app import authenticated_service
from app.dao import inbound_sms_dao
from app.v2.errors import BadRequestError
from app.v2.inbound_sms import v2_inbound_sms_blueprint


@v2_inbound_sms_blueprint.route("/<user_number>", methods=['GET'])
def get_inbound_sms_by_number(user_number):
    try:
        validate_and_format_phone_number(user_number)
    except InvalidPhoneError as e:
        raise BadRequestError(message=str(e))

    inbound_sms = inbound_sms_dao.dao_get_inbound_sms_for_service(
        authenticated_service.id, user_number=user_number
    )

    return jsonify(inbound_sms_list=[i.serialize() for i in inbound_sms]), 200


@v2_inbound_sms_blueprint.route("", methods=['GET'])
def get_all_inbound_sms():
    all_inbound_sms = inbound_sms_dao.dao_get_inbound_sms_for_service(
        authenticated_service.id
    )

    return jsonify(inbound_sms_list=[i.serialize() for i in all_inbound_sms]), 200
