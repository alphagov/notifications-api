from flask import (
    Blueprint,
    jsonify,
    current_app
)

from itsdangerous import SignatureExpired

from notifications_utils.url_safe_token import check_token

from app.dao.invited_user_dao import get_invited_user_by_id

from app.errors import (
    register_errors,
    InvalidRequest
)

from app.schemas import invited_user_schema


accept_invite = Blueprint('accept_invite', __name__)
register_errors(accept_invite)


@accept_invite.route('/<token>', methods=['GET'])
def get_invited_user_by_token(token):

    max_age_seconds = 60 * 60 * 24 * current_app.config['INVITATION_EXPIRATION_DAYS']

    try:
        invited_user_id = check_token(token,
                                      current_app.config['SECRET_KEY'],
                                      current_app.config['DANGEROUS_SALT'],
                                      max_age_seconds)
    except SignatureExpired:
        errors = {'invitation': ['Invitation has expired']}
        raise InvalidRequest(errors, status_code=400)

    invited_user = get_invited_user_by_id(invited_user_id)

    return jsonify(data=invited_user_schema.dump(invited_user).data), 200
