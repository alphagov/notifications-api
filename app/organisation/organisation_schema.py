from app.constants import (
    INVITED_USER_STATUS_TYPES,
    ORGANISATION_PERMISSION_TYPES,
    ORGANISATION_TYPES,
    OrganisationUserPermissionTypes,
)
from app.schema_validation.definitions import uuid

post_create_organisation_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST organisation schema",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "active": {"type": ["boolean", "null"]},
        "crown": {"type": "boolean"},
        "organisation_type": {"enum": ORGANISATION_TYPES},
    },
    "required": ["name", "crown", "organisation_type"],
}

post_update_organisation_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST organisation schema",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "active": {"type": ["boolean", "null"]},
        "crown": {"type": ["boolean", "null"]},
        "organisation_type": {"enum": ORGANISATION_TYPES},
        "permissions": {"type": "array", "items": {"enum": ORGANISATION_PERMISSION_TYPES}},
    },
    "required": [],
}

post_link_service_to_organisation_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST link service to organisation schema",
    "type": "object",
    "properties": {"service_id": uuid},
    "required": ["service_id"],
}


post_create_invited_org_user_status_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create organisation invite schema",
    "type": "object",
    "properties": {
        "email_address": {"type": "string", "format": "email_address"},
        "invited_by": uuid,
        "invite_link_host": {"type": "string"},
        "permissions": {
            "type": "array",
            "items": {"type": "string", "enum": [OrganisationUserPermissionTypes.can_make_services_live.value]},
        },
    },
    "required": ["email_address", "invited_by"],
}


post_update_invited_org_user_status_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update organisation invite schema",
    "type": "object",
    "properties": {"status": {"enum": INVITED_USER_STATUS_TYPES}},
    "required": ["status"],
}


post_update_org_email_branding_pool_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update organisation email branding pool schema",
    "type": "object",
    "properties": {"branding_ids": {"type": "array", "items": uuid}},
    "required": ["branding_ids"],
}


post_update_org_letter_branding_pool_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update organisation letter branding pool schema",
    "type": "object",
    "properties": {"branding_ids": {"type": "array", "items": uuid}},
    "required": ["branding_ids"],
}

post_notify_org_member_about_next_steps_of_go_live_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST notify org member about next steps of go live request",
    "type": "object",
    "properties": {
        "to": {"type": "string", "format": "email_address"},
        "service_name": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["to", "service_name", "body"],
}

post_notify_service_member_of_rejected_request_to_go_live = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST notify service member of rejected request to go live",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "service_name": {"type": "string"},
        "organisation_team_member_name": {"type": "string"},
        "organisation_team_member_email": {"type": "string"},
        "reason": {"type": "string"},
        "organisation_name": {"type": "string"},
    },
    "required": [
        "name",
        "service_name",
        "organisation_name",
        "reason",
        "organisation_team_member_name",
        "organisation_team_member_email",
    ],
}
