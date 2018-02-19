from flask import (
    Blueprint,
    request,
    jsonify,
    current_app)
from notifications_utils.url_safe_token import generate_token

from app.config import QueueNames
from app.dao.invited_org_user_dao import (
    save_invited_org_user,
    get_invited_org_user,
    get_invited_org_users_for_organisation
)
from app.dao.templates_dao import dao_get_template_by_id
from app.errors import register_errors
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, InvitedOrganisationUser
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.schema_validation import validate
from app.organisation.organisation_schema import (
    post_create_invited_org_user_status_schema,
    post_update_invited_org_user_status_schema
)

organisation_invite_blueprint = Blueprint(
    'organisation_invite', __name__,
    url_prefix='/organisation/<uuid:organisation_id>/invite')

register_errors(organisation_invite_blueprint)


@organisation_invite_blueprint.route('', methods=['POST'])
def create_invited_org_user(organisation_id):
    data = request.get_json()
    validate(data, post_create_invited_org_user_status_schema)

    invited_org_user = InvitedOrganisationUser(
        email_address=data['email_address'],
        invited_by_id=data['invited_by'],
        organisation_id=organisation_id
    )
    save_invited_org_user(invited_org_user)

    template = dao_get_template_by_id(current_app.config['ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_org_user.email_address,
        service=template.service,
        personalisation={
            'user_name': invited_org_user.invited_by.name,
            'org_name': invited_org_user.organisation.name,
            'url': invited_org_user_url(
                invited_org_user.id,
                data.get('invite_link_host'),
            ),
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=invited_org_user.from_user.email_address
    )

    send_notification_to_queue(saved_notification, research_mode=False, queue=QueueNames.NOTIFY)

    return jsonify(data=invited_org_user.serialize()), 201


@organisation_invite_blueprint.route('', methods=['GET'])
def get_invited_org_users_by_organisation(organisation_id):
    invited_org_users = get_invited_org_users_for_organisation(organisation_id)
    return jsonify(data=[x.serialize() for x in invited_org_users]), 200


@organisation_invite_blueprint.route('/<invited_org_user_id>', methods=['POST'])
def update_invited_org_user_status(organisation_id, invited_org_user_id):
    fetched = get_invited_org_user(organisation_id=organisation_id, invited_org_user_id=invited_org_user_id)

    data = request.get_json()
    validate(data, post_update_invited_org_user_status_schema)

    fetched.status = data['status']
    save_invited_org_user(fetched)
    return jsonify(data=fetched.serialize()), 200


def invited_org_user_url(invited_org_user_id, invite_link_host=None):
    token = generate_token(
        str(invited_org_user_id),
        current_app.config['SECRET_KEY'],
        current_app.config['DANGEROUS_SALT']
    )

    if invite_link_host is None:
        invite_link_host = current_app.config['ADMIN_BASE_URL']

    return '{0}/organisation-invitation/{1}'.format(invite_link_host, token)
