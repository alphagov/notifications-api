from flask import Blueprint

from app.v2.errors import register_errors

v2_inbound_sms_blueprint = Blueprint("v2_inbound_sms", __name__, url_prefix='/v2/received-text-messages')

register_errors(v2_inbound_sms_blueprint)
