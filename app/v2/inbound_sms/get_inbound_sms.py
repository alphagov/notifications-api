from flask import current_app, jsonify, request, url_for

from app import api_user, authenticated_service
from app.constants import KEY_TYPE_NORMAL
from app.dao import inbound_sms_dao
from app.schema_validation import validate
from app.v2.errors import BadRequestError
from app.v2.inbound_sms import v2_inbound_sms_blueprint
from app.v2.inbound_sms.inbound_sms_schemas import get_inbound_sms_request


@v2_inbound_sms_blueprint.route("", methods=["GET"])
def get_inbound_sms():
    # TODO: remove the check for authenticated_service.id when we have updated functional tests to use
    # a live key when hitting this endpoint
    if api_user.key_type != KEY_TYPE_NORMAL and authenticated_service.id not in (
        "07d45b34-240b-462c-8bf3-e8e3502d5f5b",  # Staging Functional Tests
        "6c1d81bb-dae2-4ee9-80b0-89a4aae9f649",  # Production Functional Tests - Providers
    ):
        raise BadRequestError(message="Cannot access received text message with team or test key", status_code=403)

    data = validate(request.args.to_dict(), get_inbound_sms_request)

    paginated_inbound_sms = inbound_sms_dao.dao_get_paginated_inbound_sms_for_service_for_public_api(
        authenticated_service.id,
        older_than=data.get("older_than", None),
        page_size=current_app.config.get("API_PAGE_SIZE"),
    )

    return (
        jsonify(
            received_text_messages=[i.serialize() for i in paginated_inbound_sms],
            links=_build_links(paginated_inbound_sms),
        ),
        200,
    )


def _build_links(inbound_sms_list):
    _links = {
        "current": url_for(
            "v2_inbound_sms.get_inbound_sms",
            _external=True,
        ),
    }

    if inbound_sms_list:
        _links["next"] = url_for(
            "v2_inbound_sms.get_inbound_sms",
            older_than=inbound_sms_list[-1].id,
            _external=True,
        )

    return _links
