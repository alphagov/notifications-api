from contextlib import suppress

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import NoResultFound

from app import db
from app.dao.date_util import parse_date_range
from app.dao.users_dao import get_users_list
from app.errors import register_errors
from app.models import (
    ApiKey,
    Complaint,
    EmailBranding,
    InboundNumber,
    InboundSms,
    Job,
    LetterBranding,
    Notification,
    Organisation,
    ProviderDetails,
    Service,
    ServiceCallbackApi,
    ServiceContactList,
    ServiceDataRetention,
    ServiceEmailReplyTo,
    ServiceSmsSender,
    Template,
    TemplateFolder,
    User,
)
from app.platform_admin.platform_admin_schemas import get_users_list_schema
from app.schema_validation import validate

platform_admin_blueprint = Blueprint("platform_admin", __name__)
register_errors(platform_admin_blueprint)

FIND_BY_UUID_MODELS = {
    "organisation": Organisation,
    "service": Service,
    "template": Template,
    "notification": Notification,
    "email_branding": EmailBranding,
    "letter_branding": LetterBranding,
    "user": User,
    "provider": ProviderDetails,
    "reply_to_email": ServiceEmailReplyTo,
    "job": Job,
    "service_contact_list": ServiceContactList,
    "service_data_retention": ServiceDataRetention,
    "service_sms_sender": ServiceSmsSender,
    "inbound_number": InboundNumber,
    "api_key": ApiKey,
    "template_folder": TemplateFolder,
    "service_callback_api": ServiceCallbackApi,
    "complaint": Complaint,
    "inbound_sms": InboundSms,
}

# The `context` here is actually information required by the admin app to build the redirect URL. This does mean
# that this endpoint and the admin search page are fairly closely coupled. We could serialize the entire object
# back, which might be more consistent with how other endpoints return representations of objects, but for many
# objects we don't need any information at all, and our serialization of objects is already inconsistently between
# `instance.serialize` and `some_schema.dump(instance)`. And not all of the serialized representations of objects
# expose the field we need anyway (which is, as of writing, invariably the related service id).
FIND_BY_UUID_EXTRA_CONTEXT = {
    "template": {"service_id"},
    "notification": {"service_id"},
    "reply_to_email": {"service_id"},
    "job": {"service_id"},
    "service_contact_list": {"service_id"},
    "service_data_retention": {"service_id"},
    "service_sms_sender": {"service_id"},
    "api_key": {"service_id"},
    "template_folder": {"service_id"},
    "service_callback_api": {"service_id"},
    "inbound_sms": {"service_id"},
}


def _find_model_by_uuid(uuid_: str) -> tuple[db.Model, str]:
    for entity_name, model in FIND_BY_UUID_MODELS.items():
        with suppress(NoResultFound):
            if instance := model.query.get(uuid_):
                return instance, entity_name

    raise NoResultFound


@platform_admin_blueprint.route("/find-by-uuid", methods=["POST"])
def find_by_uuid():
    """Provides a simple interface for looking whether a UUID references any common DB objects"""
    instance, entity_name = _find_model_by_uuid(request.json["uuid"])

    return (
        jsonify(
            {
                "type": entity_name,
                "context": {
                    field_name: getattr(instance, field_name)
                    for field_name in FIND_BY_UUID_EXTRA_CONTEXT.get(entity_name, set())
                },
            }
        ),
        200,
    )


@platform_admin_blueprint.route("/users-list", methods=["POST"])
def fetch_users_list():
    data = request.get_json()
    validate(data, get_users_list_schema)

    users = get_users_list(
        logged_in_start=parse_date_range(data.get("logged_in_start")),
        logged_in_end=parse_date_range(data.get("logged_in_end"), is_end=True),
        created_start=parse_date_range(data.get("created_start")),
        created_end=parse_date_range(data.get("created_end"), is_end=True),
        take_part_in_research=data.get("take_part_in_research"),
    )

    return jsonify(data=[user.serialize(service_filter_keys=["name"]) for user in users]), 200
