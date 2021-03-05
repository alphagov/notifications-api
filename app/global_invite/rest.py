from flask import Blueprint, current_app, jsonify
from itsdangerous import BadData, SignatureExpired
from notifications_utils.url_safe_token import check_token

from app.dao.invited_user_dao import get_invited_user_by_id
from app.dao.organisation_dao import dao_get_invited_organisation_user
from app.errors import InvalidRequest, register_errors
from app.schemas import invited_user_schema

global_invite_blueprint = Blueprint('global_invite', __name__)
register_errors(global_invite_blueprint)


@global_invite_blueprint.route('/<invitation_type>/<token>', methods=['GET'])
def validate_invitation_token(invitation_type, token):

    max_age_seconds = 60 * 60 * 24 * current_app.config['INVITATION_EXPIRATION_DAYS']

    try:
        invited_user_id = check_token(token,
                                      current_app.config['SECRET_KEY'],
                                      current_app.config['DANGEROUS_SALT'],
                                      max_age_seconds)
    except SignatureExpired:
        errors = {'invitation':
                  'Your invitation to GOV.UK Notify has expired. '
                  'Please ask the person that invited you to send you another one'}
        raise InvalidRequest(errors, status_code=400)
    except BadData:
        errors = {'invitation': 'Something’s wrong with this link. Make sure you’ve copied the whole thing.'}
        raise InvalidRequest(errors, status_code=400)

    if invitation_type == 'service':
        invited_user = get_invited_user_by_id(invited_user_id)
        return jsonify(data=invited_user_schema.dump(invited_user).data), 200
    elif invitation_type == 'organisation':
        invited_user = dao_get_invited_organisation_user(invited_user_id)
        return jsonify(data=invited_user.serialize()), 200
    else:
        raise InvalidRequest("Unrecognised invitation type: {}".format(invitation_type))


@global_invite_blueprint.route('/service/<uuid:invited_user_id>', methods=['GET'])
def get_invited_user(invited_user_id):
    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user).data), 200


@global_invite_blueprint.route('/organisation/<uuid:invited_org_user_id>', methods=['GET'])
def get_invited_org_user(invited_org_user_id):
    invited_user = dao_get_invited_organisation_user(invited_org_user_id)
    return jsonify(data=invited_user.serialize()), 200
