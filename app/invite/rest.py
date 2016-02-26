from flask import (
    Blueprint,
    request,
    jsonify
)

from app.dao.invited_user_dao import (
    save_invited_user,
    get_invited_user,
    get_invited_users_for_service
)

from app.schemas import invited_user_schema

invite = Blueprint('invite', __name__, url_prefix='/service/<service_id>/invite')

from app.errors import register_errors
register_errors(invite)


@invite.route('', methods=['POST'])
def create_invited_user(service_id):
    invited_user, errors = invited_user_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    save_invited_user(invited_user)
    return jsonify(data=invited_user_schema.dump(invited_user).data), 201


@invite.route('', methods=['GET'])
def get_invited_users_by_service(service_id):
    invited_users = get_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(invited_users, many=True).data), 200


@invite.route('/<invited_user_id>', methods=['GET'])
def get_invited_user_by_service_and_id(service_id, invited_user_id):
    invited_user = get_invited_user(service_id, invited_user_id)
    if not invited_user:
        message = 'Invited user not found for service id: {} and invited user id: {}'.format(service_id,
                                                                                             invited_user_id)
        return jsonify(result='error', message=message), 404
    return jsonify(data=invited_user_schema.dump(invited_user).data), 200
