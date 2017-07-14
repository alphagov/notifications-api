from flask import (
    Blueprint,
    request,
    jsonify,
    current_app)

from app.celery import QueueNames
from app.dao.invited_user_dao import (
    save_invited_user,
    get_invited_user,
    get_invited_users_for_service
)
from app.dao.templates_dao import dao_get_template_by_id
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, Service
from app.notifications.process_notifications import persist_notification, send_notification_to_queue
from app.schemas import invited_user_schema

invite = Blueprint('invite', __name__, url_prefix='/service/<service_id>/invite')

from app.errors import register_errors

register_errors(invite)


@invite.route('', methods=['POST'])
def create_invited_user(service_id):
    invited_user, errors = invited_user_schema.load(request.get_json())
    save_invited_user(invited_user)

    template = dao_get_template_by_id(current_app.config['INVITATION_EMAIL_TEMPLATE_ID'])
    service = Service.query.get(current_app.config['NOTIFY_SERVICE_ID'])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_user.email_address,
        service=service,
        personalisation={
            'user_name': invited_user.from_user.name,
            'service_name': invited_user.service.name,
            'url': invited_user_url(invited_user.id)
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL
    )

    send_notification_to_queue(saved_notification, False, queue=QueueNames.NOTIFY)

    return jsonify(data=invited_user_schema.dump(invited_user).data), 201


@invite.route('', methods=['GET'])
def get_invited_users_by_service(service_id):
    invited_users = get_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(invited_users, many=True).data), 200


@invite.route('/<invited_user_id>', methods=['GET'])
def get_invited_user_by_service_and_id(service_id, invited_user_id):
    invited_user = get_invited_user(service_id=service_id, invited_user_id=invited_user_id)

    return jsonify(data=invited_user_schema.dump(invited_user).data), 200


@invite.route('/<invited_user_id>', methods=['POST'])
def update_invited_user(service_id, invited_user_id):
    fetched = get_invited_user(service_id=service_id, invited_user_id=invited_user_id)

    current_data = dict(invited_user_schema.dump(fetched).data.items())
    current_data.update(request.get_json())
    update_dict = invited_user_schema.load(current_data).data
    save_invited_user(update_dict)
    return jsonify(data=invited_user_schema.dump(fetched).data), 200


def invited_user_url(invited_user_id):
    from notifications_utils.url_safe_token import generate_token
    token = generate_token(str(invited_user_id), current_app.config['SECRET_KEY'], current_app.config['DANGEROUS_SALT'])

    return '{0}/invitation/{1}'.format(current_app.config['ADMIN_BASE_URL'], token)
