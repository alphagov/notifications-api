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
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, InvitedOrganisationUser
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.schemas import invited_org_user_schema
from app.errors import register_errors

invite = Blueprint('invite', __name__, url_prefix='/organisation/<organisation_id>/invite')

register_errors(invite)


@invite.route('', methods=['POST'])
def create_invited_org_user(organisation_id):
    request_json = request.get_json()

    invited_org_user = InvitedOrganisationUser(
        email_address=request_json['email_address'],
        invited_by_id=request_json['invited_by'],
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
                request_json.get('invite_link_host'),
            ),
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=invited_org_user.from_user.email_address
    )

    send_notification_to_queue(saved_notification, research_mode=False, queue=QueueNames.NOTIFY)

    return jsonify(data=invited_org_user.serialize()), 201


@invite.route('', methods=['GET'])
def get_invited_org_users_by_organisation(organisation_id):
    invited_org_users = get_invited_org_users_for_organisation(organisation_id)
    return jsonify(data=[x.serialize() for x in invited_org_users]), 200


@invite.route('/<invited_org_user_id>', methods=['POST'])
def update_invited_org_user(organisation_id, invited_org_user_id):
    fetched = get_invited_org_user(organisation_id=organisation_id, invited_org_user_id=invited_org_user_id)

    current_data = dict(fetched.serialize().items())
    current_data.update(request.get_json())
    update_dict = invited_org_user_schema.load(current_data).data
    save_invited_org_user(update_dict)
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
