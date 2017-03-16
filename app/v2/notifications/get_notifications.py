import uuid

from flask import jsonify, request, url_for, current_app
from werkzeug.exceptions import abort

from app import api_user
from app.dao import notifications_dao
from app.schema_validation import validate
from app.v2.notifications import v2_notification_blueprint
from app.v2.notifications.notification_schemas import get_notifications_request


@v2_notification_blueprint.route("/<id>", methods=['GET'])
def get_notification_by_id(id):
    try:
        casted_id = uuid.UUID(id)
    except ValueError or AttributeError:
        abort(404)
    notification = notifications_dao.get_notification_with_personalisation(
        api_user.service_id, casted_id, key_type=None
    )

    return jsonify(notification.serialize()), 200


@v2_notification_blueprint.route("", methods=['GET'])
def get_notifications():
    _data = request.args.to_dict(flat=False)

    # flat=False makes everything a list, but we only ever allow one value for "older_than"
    if 'older_than' in _data:
        _data['older_than'] = _data['older_than'][0]

    # and client reference
    if 'reference' in _data:
        _data['reference'] = _data['reference'][0]

    data = validate(_data, get_notifications_request)

    paginated_notifications = notifications_dao.get_notifications_for_service(
        str(api_user.service_id),
        filter_dict=data,
        key_type=api_user.key_type,
        personalisation=True,
        older_than=data.get('older_than'),
        client_reference=data.get('reference'),
        page_size=current_app.config.get('API_PAGE_SIZE')
    )

    def _build_links(notifications):
        _links = {
            'current': url_for(".get_notifications", _external=True, **data),
        }

        if len(notifications):
            next_query_params = dict(data, older_than=notifications[-1].id)
            _links['next'] = url_for(".get_notifications", _external=True, **next_query_params)

        return _links

    return jsonify(
        notifications=[notification.serialize() for notification in paginated_notifications.items],
        links=_build_links(paginated_notifications.items)
    ), 200
