from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.config import QueueNames
from app.constants import INVITE_PENDING, KEY_TYPE_NORMAL, NHS_ORGANISATION_TYPES, OrganisationUserPermissionTypes
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.dao_utils import transaction
from app.dao.fact_billing_dao import fetch_usage_for_organisation
from app.dao.invited_org_user_dao import get_invited_org_users_for_organisation
from app.dao.organisation_dao import (
    dao_add_email_branding_list_to_organisation_pool,
    dao_add_letter_branding_list_to_organisation_pool,
    dao_add_service_to_organisation,
    dao_add_user_to_organisation,
    dao_archive_organisation,
    dao_create_organisation,
    dao_get_email_branding_pool_for_organisation,
    dao_get_letter_branding_pool_for_organisation,
    dao_get_organisation_by_email_address,
    dao_get_organisation_by_id,
    dao_get_organisation_services,
    dao_get_organisations,
    dao_get_organisations_by_partial_name,
    dao_get_users_for_organisation,
    dao_remove_email_branding_from_organisation_pool,
    dao_remove_letter_branding_from_organisation_pool,
    dao_remove_user_from_organisation,
    dao_update_organisation,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.templates_dao import dao_get_template_by_id
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest, register_errors
from app.models import Organisation
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.organisation.organisation_schema import (
    post_create_organisation_schema,
    post_link_service_to_organisation_schema,
    post_notify_org_member_about_next_steps_of_go_live_request,
    post_notify_service_member_of_rejected_go_live_request,
    post_update_org_email_branding_pool_schema,
    post_update_org_letter_branding_pool_schema,
    post_update_organisation_schema,
)
from app.organisation.sender import send_notification_to_organisation_users
from app.schema_validation import validate

organisation_blueprint = Blueprint("organisation", __name__)
register_errors(organisation_blueprint)


@organisation_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organisation_name
    """
    if "ix_organisation_name" in str(exc):
        return jsonify(result="error", message="Organisation name already exists"), 400
    if 'duplicate key value violates unique constraint "domain_pkey"' in str(exc):
        return jsonify(result="error", message="Domain already exists"), 400

    current_app.logger.exception(exc)
    return jsonify(result="error", message="Internal server error"), 500


@organisation_blueprint.route("", methods=["GET"])
def get_organisations():
    organisations = [org.serialize_for_list() for org in dao_get_organisations()]

    return jsonify(organisations)


@organisation_blueprint.route("/<uuid:organisation_id>", methods=["GET"])
def get_organisation_by_id(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    return jsonify(organisation.serialize())


@organisation_blueprint.route("/by-domain", methods=["GET"])
def get_organisation_by_domain():
    domain = request.args.get("domain")

    if not domain or "@" in domain:
        abort(400)

    organisation = dao_get_organisation_by_email_address("example@{}".format(request.args.get("domain")))

    if not organisation:
        abort(404)

    return jsonify(organisation.serialize())


@organisation_blueprint.route("/search", methods=["GET"])
def search():
    organisation_name = request.args.get("name")
    if not organisation_name:
        errors = {"name": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    fetched_organisations = dao_get_organisations_by_partial_name(organisation_name)
    data = [organisation.serialize_for_list() for organisation in fetched_organisations]
    return jsonify(data=data), 200


@organisation_blueprint.route("", methods=["POST"])
def create_organisation():
    data = request.get_json()

    validate(data, post_create_organisation_schema)

    organisation = Organisation(**data)
    dao_create_organisation(organisation)

    return jsonify(organisation.serialize()), 201


@organisation_blueprint.route("/<uuid:organisation_id>", methods=["POST"])
def update_organisation(organisation_id):
    data = request.get_json()
    validate(data, post_update_organisation_schema)

    organisation = dao_get_organisation_by_id(organisation_id)

    if data.get("organisation_type") in NHS_ORGANISATION_TYPES:
        if not organisation.email_branding_id:
            data["email_branding_id"] = current_app.config["NHS_EMAIL_BRANDING_ID"]
        if not organisation.letter_branding_id:
            data["letter_branding_id"] = current_app.config["NHS_LETTER_BRANDING_ID"]

    if data.get("permissions") or data.get("permissions") == []:
        organisation.set_permissions_list(data.get("permissions"))
        result = True
    else:
        result = dao_update_organisation(organisation_id, **data)

    if data.get("agreement_signed") is True:
        # if a platform admin has manually adjusted the organisation, don't tell people
        if data.get("agreement_signed_by_id"):
            send_notifications_on_mou_signed(organisation_id)

    if result:
        return "", 204
    else:
        raise InvalidRequest("Organisation not found", 404)


@organisation_blueprint.route("/<uuid:organisation_id>/archive", methods=["POST"])
def archive_organisation(organisation_id):
    """
    All services must be reassigned and all team members removed before an org can be
    archived.
    When an org is archived, its email branding, letter branding and any domains are deleted.
    """

    organisation = dao_get_organisation_by_id(organisation_id)

    if any(service.active for service in organisation.services):
        raise InvalidRequest("Cannot archive an organisation with active services", 400)

    pending_invited_users = [
        user for user in get_invited_org_users_for_organisation(organisation_id) if user.status == INVITE_PENDING
    ]

    if organisation.users or pending_invited_users:
        raise InvalidRequest("Cannot archive an organisation with team members or invited team members", 400)

    if organisation.active:
        dao_archive_organisation(organisation_id)

    return "", 204


@organisation_blueprint.route("/<uuid:organisation_id>/service", methods=["POST"])
def link_service_to_organisation(organisation_id):
    data = request.get_json()
    validate(data, post_link_service_to_organisation_schema)
    service = dao_fetch_service_by_id(data["service_id"])
    service.organisation = None

    with transaction():
        dao_add_service_to_organisation(service, organisation_id)
        set_default_free_allowance_for_service(service, year_start=None)

    return "", 204


@organisation_blueprint.route("/<uuid:organisation_id>/services", methods=["GET"])
def get_organisation_services(organisation_id):
    services = dao_get_organisation_services(organisation_id)
    sorted_services = sorted(services, key=lambda s: (-s.active, s.name))
    return jsonify([s.serialize_for_org_dashboard() for s in sorted_services])


@organisation_blueprint.route("/<uuid:organisation_id>/services-with-usage", methods=["GET"])
def get_organisation_services_usage(organisation_id):
    try:
        year = int(request.args.get("year", "none"))
    except ValueError:
        return jsonify(result="error", message="No valid year provided"), 400
    services, updated_at = fetch_usage_for_organisation(organisation_id, year)
    list_services = services.values()
    sorted_services = sorted(list_services, key=lambda s: (-s["active"], s["service_name"].lower()))
    return jsonify(services=sorted_services, updated_at=updated_at)


@organisation_blueprint.route("/<uuid:organisation_id>/users/<uuid:user_id>", methods=["POST"])
def add_user_to_organisation(organisation_id, user_id):
    permissions = [p["permission"] for p in request.get_json()["permissions"]]
    new_org_user = dao_add_user_to_organisation(organisation_id, user_id, permissions)
    return jsonify(data=new_org_user.serialize())


@organisation_blueprint.route("/<uuid:organisation_id>/users/<uuid:user_id>", methods=["DELETE"])
def remove_user_from_organisation(organisation_id, user_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    user = get_user_by_id(user_id=user_id)

    if user not in organisation.users:
        error = "User not found"
        raise InvalidRequest(error, status_code=404)

    dao_remove_user_from_organisation(organisation, user)

    return {}, 204


@organisation_blueprint.route("/<uuid:organisation_id>/users", methods=["GET"])
def get_organisation_users(organisation_id):
    org_users = dao_get_users_for_organisation(organisation_id)
    return jsonify(data=[x.serialize() for x in org_users])


@organisation_blueprint.route("/<uuid:organisation_id>/email-branding-pool", methods=["GET"])
def get_organisation_email_branding_pool(organisation_id):
    branding_pool = dao_get_email_branding_pool_for_organisation(organisation_id)
    return jsonify(data=[branding.serialize() for branding in branding_pool])


@organisation_blueprint.route("/<uuid:organisation_id>/email-branding-pool", methods=["POST"])
def update_organisation_email_branding_pool(organisation_id):
    data = request.get_json()
    validate(data, post_update_org_email_branding_pool_schema)

    dao_add_email_branding_list_to_organisation_pool(organisation_id, data["branding_ids"])

    return {}, 204


@organisation_blueprint.route(
    "/<uuid:organisation_id>/email-branding-pool/<uuid:email_branding_id>", methods=["DELETE"]
)
def remove_email_branding_from_organisation_pool(organisation_id, email_branding_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    email_branding_ids = {eb.id for eb in organisation.email_branding_pool}

    if email_branding_id not in email_branding_ids:
        error = f"Email branding {email_branding_id} not in {organisation}'s pool"
        raise InvalidRequest(error, status_code=404)

    dao_remove_email_branding_from_organisation_pool(organisation_id, email_branding_id)

    return {}, 204


@organisation_blueprint.route("/<uuid:organisation_id>/letter-branding-pool", methods=["GET"])
def get_organisation_letter_branding_pool(organisation_id):
    branding_pool = dao_get_letter_branding_pool_for_organisation(organisation_id)
    return jsonify(data=[branding.serialize() for branding in branding_pool])


@organisation_blueprint.route("/<uuid:organisation_id>/letter-branding-pool", methods=["POST"])
def update_organisation_letter_branding_pool(organisation_id):
    data = request.get_json()
    validate(data, post_update_org_letter_branding_pool_schema)

    dao_add_letter_branding_list_to_organisation_pool(organisation_id, data["branding_ids"])

    return {}, 204


@organisation_blueprint.route(
    "/<uuid:organisation_id>/letter-branding-pool/<uuid:letter_branding_id>", methods=["DELETE"]
)
def remove_letter_branding_from_organisation_pool(organisation_id, letter_branding_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    letter_branding_ids = {branding.id for branding in organisation.letter_branding_pool}

    if letter_branding_id not in letter_branding_ids:
        raise InvalidRequest(f"Letter branding {letter_branding_id} not in {organisation.name}'s pool", status_code=404)

    if organisation.letter_branding_id == letter_branding_id:
        raise InvalidRequest("You cannot remove an organisation's default letter branding", status_code=400)

    dao_remove_letter_branding_from_organisation_pool(organisation_id, letter_branding_id)

    return {}, 204


@organisation_blueprint.route("/notify-users-of-request-to-go-live/<uuid:service_id>", methods=["POST"])
def notify_users_of_request_to_go_live(service_id):
    template = dao_get_template_by_id(current_app.config["GO_LIVE_NEW_REQUEST_FOR_ORG_USERS_TEMPLATE_ID"])
    service = dao_fetch_service_by_id(service_id)
    organisation = service.organisation
    make_service_live_link = f"{current_app.config['ADMIN_BASE_URL']}/services/{service.id}/make-service-live"
    support_page_link = f"{current_app.config['ADMIN_BASE_URL']}/support"

    send_notification_to_organisation_users(
        organisation=organisation,
        template=template,
        reply_to_text=service.go_live_user.email_address,
        with_permission=OrganisationUserPermissionTypes.can_make_services_live,
        personalisation={
            "service_name": service.name,
            "requester_name": service.go_live_user.name,
            "requester_email_address": service.go_live_user.email_address,
            "make_service_live_link": make_service_live_link,
            "support_page_link": support_page_link,
            "organisation_name": organisation.name,
        },
        include_user_fields={"name"},
    )

    return {}, 204


@organisation_blueprint.route(
    "/notify-org-member-about-next-steps-of-go-live-request/<uuid:service_id>", methods=["POST"]
)
def notify_org_member_about_next_steps_of_go_live_request(service_id):
    data = request.get_json()
    validate(data, post_notify_org_member_about_next_steps_of_go_live_request)

    template = dao_get_template_by_id(current_app.config["GO_LIVE_REQUEST_NEXT_STEPS_FOR_ORG_USER_TEMPLATE_ID"])
    service = dao_fetch_service_by_id(service_id)
    if not service.go_live_user or not service.has_active_go_live_request:
        abort(400)

    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=data["to"],
        service=notify_service,
        personalisation={"service_name": data["service_name"], "body": data["body"]},
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=notify_service.get_default_reply_to_email_address(),
    )
    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    return {}, 204


@organisation_blueprint.route("/notify-service-member-of-rejected-go-live-request/<uuid:service_id>", methods=["POST"])
def notify_service_member_of_rejected_go_live_request(service_id):
    data = request.get_json()
    validate(data, post_notify_service_member_of_rejected_go_live_request)

    template = dao_get_template_by_id(current_app.config["GO_LIVE_REQUEST_REJECTED_BY_ORG_USER_TEMPLATE_ID"])
    service = dao_fetch_service_by_id(service_id)
    if not service.go_live_user or not service.has_active_go_live_request:
        abort(400)

    # Add carets before each line of the rejection reason so that it appears as inset text.
    data["reason"] = "\n".join(f"^ {line}" for line in data["reason"].split("\n"))

    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])
    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=service.go_live_user.email_address,
        service=notify_service,
        personalisation={
            "name": data["name"],
            "service_name": data["service_name"],
            "organisation_name": data["organisation_name"],
            "reason": data["reason"],
            "organisation_team_member_name": data["organisation_team_member_name"],
            "organisation_team_member_email": data["organisation_team_member_email"],
        },
        notification_type=template.template_type,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=notify_service.get_default_reply_to_email_address(),
    )
    send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    return {}, 204


def send_notifications_on_mou_signed(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    def _send_notification(template_id, recipient, personalisation):
        template = dao_get_template_by_id(template_id)

        saved_notification = persist_notification(
            template_id=template.id,
            template_version=template.version,
            recipient=recipient,
            service=notify_service,
            personalisation=personalisation,
            notification_type=template.template_type,
            api_key_id=None,
            key_type=KEY_TYPE_NORMAL,
            reply_to_text=notify_service.get_default_reply_to_email_address(),
        )
        send_notification_to_queue(saved_notification, queue=QueueNames.NOTIFY)

    personalisation = {
        "mou_link": "{}/agreement/{}.pdf".format(
            current_app.config["ADMIN_BASE_URL"], "crown" if organisation.crown else "non-crown"
        ),
        "org_name": organisation.name,
        "org_dashboard_link": "{}/organisations/{}".format(current_app.config["ADMIN_BASE_URL"], organisation.id),
        "signed_by_name": organisation.agreement_signed_by.name,
        "on_behalf_of_name": organisation.agreement_signed_on_behalf_of_name,
    }

    if not organisation.agreement_signed_on_behalf_of_email_address:
        signer_template_id = "MOU_SIGNER_RECEIPT_TEMPLATE_ID"
    else:
        signer_template_id = "MOU_SIGNED_ON_BEHALF_SIGNER_RECEIPT_TEMPLATE_ID"

        # let the person who has been signed on behalf of know.
        _send_notification(
            current_app.config["MOU_SIGNED_ON_BEHALF_ON_BEHALF_RECEIPT_TEMPLATE_ID"],
            organisation.agreement_signed_on_behalf_of_email_address,
            personalisation,
        )

    # let the person who signed know - the template is different depending on if they signed on behalf of someone
    _send_notification(
        current_app.config[signer_template_id], organisation.agreement_signed_by.email_address, personalisation
    )
