from datetime import timedelta

from flask import (
    Blueprint,
    request,
    jsonify,
    current_app)

from app import encryption
from app.dao.invited_user_dao import (
    save_invited_user,
    get_invited_user,
    get_invited_users_for_service
)

from app.schemas import invited_user_schema
from app.celery.tasks import (email_invited_user)

invite = Blueprint('invite', __name__, url_prefix='/service/<service_id>/invite')

from app.errors import register_errors
register_errors(invite)


@invite.route('', methods=['POST'])
def create_invited_user(service_id):
    invited_user, errors = invited_user_schema.load(request.get_json())
    if errors:
        return jsonify(result="error", message=errors), 400
    save_invited_user(invited_user)
    invitation = _create_invitation(invited_user)
    encrypted_invitation = encryption.encrypt(invitation)
    email_invited_user.apply_async([encrypted_invitation], queue='email-invited-user')
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


def _create_invitation(invited_user):
    from utils.url_safe_token import generate_token
    token = generate_token(str(invited_user.id), current_app.config['SECRET_KEY'], current_app.config['DANGEROUS_SALT'])
    # TODO: confirm what we want to do for this - the idea is that we say expires tomorrow at midnight
    # and give 48 hours as the max_age
    expiration_date = (invited_user.created_at + timedelta(days=current_app.config['INVITATION_EXPIRATION_DAYS'])) \
        .replace(hour=0, minute=0, second=0, microsecond=0)

    invitation = {'to': invited_user.email_address,
                  'user_name': invited_user.from_user.name,
                  'service_id': str(invited_user.service_id),
                  'service_name': invited_user.service.name,
                  'token': token,
                  'expiry_date': str(expiration_date)
                  }
    return invitation
