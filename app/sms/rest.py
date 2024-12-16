from flask import Blueprint, jsonify

from app.dao.sms_rate_dao import dao_get_current_sms_rate
from app.v2.errors.errors import register_errors

sms_rate_blueprint = Blueprint("sms_rate", __name__, url_prefix="/sms-rate")
register_errors(sms_rate_blueprint)


@sms_rate_blueprint.route("/", methods=["GET"])
def get_sms_rate():
    return jsonify(dao_get_current_sms_rate().serialize())
