from flask import (
    Blueprint,
    request,
    jsonify
)

from app.dao.invited_user_dao import save_invited_user
from app.schemas import invited_user_schema

invite = Blueprint('invite', __name__, url_prefix='/service/<service_id>/invite')

from app.errors import register_errors
register_errors(invite)


@invite.route('', methods=['POST'])
def create_invite_user(service_id):
    invited_user, errors = invited_user_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400

    save_invited_user(invited_user)

    return jsonify(data=invited_user_schema.dump(invited_user).data), 201
