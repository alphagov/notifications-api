from flask import Blueprint, jsonify, current_app
from itsdangerous import SignatureExpired
from notifications_utils.url_safe_token import check_token

from app.dao.organisation_dao import dao_get_invited_organisation_user
from app.errors import register_errors, InvalidRequest

accept_organisation_invite_blueprint = Blueprint(
    'accept_organisation_invite', __name__,
    url_prefix='/organisation-invitation')

register_errors(accept_organisation_invite_blueprint)


@accept_organisation_invite_blueprint.route("/<token>", methods=['GET'])
def accept_organisation_invitation(token):
    max_age_seconds = 60 * 60 * 24 * current_app.config['INVITATION_EXPIRATION_DAYS']

    try:
        invited_user_id = check_token(token,
                                      current_app.config['SECRET_KEY'],
                                      current_app.config['DANGEROUS_SALT'],
                                      max_age_seconds)
    except SignatureExpired:
        errors = {'invitation': ['Your invitation to GOV.UK Notify has expired. '
                                 'Please ask the person that invited you to send you another one']}
        raise InvalidRequest(errors, status_code=400)
    invited_user = dao_get_invited_organisation_user(invited_user_id)

    return jsonify(data=invited_user.serialize()), 200
