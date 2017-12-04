from flask import jsonify, request, url_for, current_app

from app import authenticated_service
from app.dao import inbound_sms_dao
from app.schema_validation import validate
from app.v2.inbound_sms import v2_inbound_sms_blueprint
from app.v2.inbound_sms.inbound_sms_schemas import get_inbound_sms_request


@v2_inbound_sms_blueprint.route("", methods=['GET'])
def get_inbound_sms():
    data = validate(request.args.to_dict(), get_inbound_sms_request)

    paginated_inbound_sms = inbound_sms_dao.dao_get_paginated_inbound_sms_for_service(
        authenticated_service.id,
        older_than=data.get('older_than', None),
        page_size=current_app.config.get('API_PAGE_SIZE')
    )

    return jsonify(
        received_text_messages=[i.serialize() for i in paginated_inbound_sms],
        links=_build_links(paginated_inbound_sms)
    ), 200


def _build_links(inbound_sms_list):
    _links = {
        'current': url_for(
            "v2_inbound_sms.get_inbound_sms",
            _external=True,
        ),
    }

    if inbound_sms_list:
        _links['next'] = url_for(
            "v2_inbound_sms.get_inbound_sms",
            older_than=inbound_sms_list[-1].id,
            _external=True,
        )

    return _links
