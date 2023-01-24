from contextlib import suppress

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import NoResultFound

from app import db
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
    ServiceInboundApi,
    ServiceSmsSender,
    Template,
    TemplateFolder,
    User,
)

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
    "service_inbound_api": ServiceInboundApi,
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
    "service_inbound_api": {"service_id"},
    "service_callback_api": {"service_id"},
    "inbound_sms": {"service_id"},
}


def _model_lookup(value: str) -> tuple[db.Model, str]:
    for entity_name, model in FIND_BY_UUID_MODELS.items():
        with suppress(NoResultFound):
            if instance := model.query.get(value):
                return instance, entity_name

    # Special case - also see if we're looking for a notification by reference
    # If we introduce any more of these, consider refactoring FIND_BY_UUID_MODELS to use a list of lookup functions
    with suppress(NoResultFound):
        if instance := Notification.query.filter_by(reference=value).one():
            return instance, "notification"

    raise NoResultFound


@platform_admin_blueprint.route("/find", methods=["POST"])
@platform_admin_blueprint.route("/find-by-uuid", methods=["POST"])
def find():
    """Provides a simple interface for looking whether a given value is associated with any common DB objects.

    'value' above means a UUID or a notification reference
    """
    value = request.json["value"] if "value" in request.json else request.json["uuid"]
    instance, entity_name = _model_lookup(value)

    return (
        jsonify(
            {
                "type": entity_name,
                "id": instance.id,
                "context": {
                    field_name: getattr(instance, field_name)
                    for field_name in FIND_BY_UUID_EXTRA_CONTEXT.get(entity_name, set())
                },
            }
        ),
        200,
    )
