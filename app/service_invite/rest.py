from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadData, SignatureExpired
from notifications_utils.url_safe_token import check_token, generate_token

from app.config import QueueNames
from app.constants import BROADCAST_TYPE, EMAIL_TYPE, KEY_TYPE_NORMAL
from app.dao.invited_user_dao import (
    get_invited_user_by_id,
    get_invited_user_by_service_and_id,
    get_invited_users_for_service,
    save_invited_user,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest, register_errors
from app.models import Service
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.schemas import invited_user_schema
from app.v2.errors import BadRequestError

service_invite = Blueprint("service_invite", __name__)

register_errors(service_invite)


@service_invite.route("/service/<service_id>/invite", methods=["POST"])
def create_invited_user(service_id):
    request_json = request.get_json()
    invited_user = invited_user_schema.load(request_json)
    save_invited_user(invited_user)

    if invited_user.service.has_permission(BROADCAST_TYPE):
        template_id = current_app.config["BROADCAST_INVITATION_EMAIL_TEMPLATE_ID"]
    else:
        template_id = current_app.config["INVITATION_EMAIL_TEMPLATE_ID"]

    template = dao_get_template_by_id(template_id)
    service = Service.query.get(current_app.config["NOTIFY_SERVICE_ID"])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_user.email_address,
        service=service,
        personalisation={
            "user_name": invited_user.from_user.name,
            "service_name": invited_user.service.name,
            "url": invited_user_url(
                invited_user.id,
                request_json.get("invite_link_host"),
            ),
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=invited_user.from_user.email_address,
    )

    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    return jsonify(data=invited_user_schema.dump(invited_user)), 201


@service_invite.route("/service/<service_id>/invite", methods=["GET"])
def get_invited_users_by_service(service_id):
    invited_users = get_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(invited_users, many=True)), 200


@service_invite.route("/service/<service_id>/invite/<invited_user_id>", methods=["GET"])
def get_invited_user_by_service(service_id, invited_user_id):
    invited_user = get_invited_user_by_service_and_id(service_id, invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route("/service/<service_id>/invite/<invited_user_id>", methods=["POST"])
def update_invited_user(service_id, invited_user_id):
    fetched = get_invited_user_by_service_and_id(service_id=service_id, invited_user_id=invited_user_id)

    current_data = dict(invited_user_schema.dump(fetched).items())
    current_data.update(request.get_json())
    update_dict = invited_user_schema.load(current_data)
    save_invited_user(update_dict)
    return jsonify(data=invited_user_schema.dump(fetched)), 200


def invited_user_url(invited_user_id, invite_link_host=None):
    token = generate_token(str(invited_user_id), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])

    if invite_link_host is None:
        invite_link_host = current_app.config["ADMIN_BASE_URL"]

    return "{0}/invitation/{1}".format(invite_link_host, token)


@service_invite.route("/invite/service/<uuid:invited_user_id>", methods=["GET"])
def get_invited_user(invited_user_id):
    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route("/invite/service/<token>", methods=["GET"])
@service_invite.route("/invite/service/check/<token>", methods=["GET"])
def validate_service_invitation_token(token):
    max_age_seconds = 60 * 60 * 24 * current_app.config["INVITATION_EXPIRATION_DAYS"]

    try:
        invited_user_id = check_token(
            token, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"], max_age_seconds
        )
    except SignatureExpired as e:
        errors = {
            "invitation": "Your invitation to GOV.UK Notify has expired. "
            "Please ask the person that invited you to send you another one"
        }
        raise InvalidRequest(errors, status_code=400) from e
    except BadData as e:
        errors = {"invitation": "Something’s wrong with this link. Make sure you’ve copied the whole thing."}
        raise InvalidRequest(errors, status_code=400) from e

    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route("/service/<service_id>/invite/request-for/<user_to_invite_id>", methods=["POST"])
def request_user_invite(service_id, user_to_invite_id):
    request_json = request.get_json()

    user_requesting_invite = get_user_by_id(user_to_invite_id)
    recipients_of_invite_request_ids = request_json["from_user_id"]
    recipients_of_invite_request = [get_user_by_id(recipient_id) for recipient_id in recipients_of_invite_request_ids]
    service = dao_fetch_service_by_id(service_id)
    reason_for_request = request_json["reason"]
    invite_link_host = request_json["invite_link_host"]
    print(invite_link_host)

    # Ensure that the user making the request is already not part of the service
    if user_requesting_invite.services and service in user_requesting_invite.services:
        message = f"You are already a member of {service.name}"
        raise BadRequestError(message=message)

    # Send the user's service invite request to the service managers listed
    send_service_invite_request(
        user_requesting_invite, recipients_of_invite_request, service, reason_for_request, invite_link_host
    )

    # Send a receipt email to the user that requested the invite
    # send_receipt_after_sending_request_invite_letter(user_requesting_invite.name, service)

    return {}, 204


def send_service_invite_request(
    user_requesting_invite, recipients_of_invite_request, service, reason_for_request, invite_link_host
):
    # TODO REQUEST_INVITE_TO_SERVICE_TEMPLATE needs to be created
    template_id = current_app.config["REQUEST_INVITE_TO_SERVICE_TEMPLATE_ID"]
    template = dao_get_template_by_id(template_id)
    notify_service = Service.query.get(current_app.config["NOTIFY_SERVICE_ID"])
    invite_link_host = invite_link_host
    for recipient in recipients_of_invite_request:
        if service in recipient.services:
            saved_notification = persist_notification(
                template_id=template.id,
                template_version=template.version,
                # TODO change recipient to actual email address of service managers when the testing phase completes
                recipient="chukwugozie.mbeledogu+request_invite_test@digital.cabinet-office.gov.uk",
                service=notify_service,
                # TODO flesh out personalisation
                personalisation={
                    "name": service.name,
                    "requester_name": user_requesting_invite.name,
                    "reason": reason_for_request,
                },
                notification_type=template.template_type,
                api_key_id=None,
                key_type=KEY_TYPE_NORMAL,
                reply_to_text=notify_service.get_default_reply_to_email_address(),
            )
            send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

        else:
            message = f"Can’t create notification - {recipient.name} is not part of the {service.name}"
            raise BadRequestError(message=message)


def send_receipt_after_sending_request_invite_letter(user_requesting_invite, service):
    # TODO RECEIPT_FOR_REQUEST_INVITE_TO_SERVICE_TEMPLATE needs to be created
    template_id = current_app.config["RECEIPT_FOR_REQUEST_INVITE_TO_SERVICE_TEMPLATE_ID"]
    template = dao_get_template_by_id(template_id)
    notify_service = Service.query.get(current_app.config["NOTIFY_SERVICE_ID"])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        # TODO change recipient to actual email address of service managers when the testing phase completes
        recipient="notify-join-service-request@digital.cabinet-office.gov.uk",
        service=notify_service,
        # TODO flesh out personalisation
        personalisation={"service_name": service, "user_requesting_invite_name": user_requesting_invite},
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=notify_service.get_default_reply_to_email_address(),
    )
    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)
