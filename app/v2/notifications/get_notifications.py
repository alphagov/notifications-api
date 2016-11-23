from flask import jsonify, request, url_for

from app import api_user
from app.dao import notifications_dao
from app.schemas import notifications_filter_schema
from app.v2.notifications import notification_blueprint


@notification_blueprint.route("/<uuid:id>", methods=['GET'])
def get_notification_by_id(id):
    notification = notifications_dao.get_notification_with_personalisation(
        str(api_user.service_id), id, key_type=None
    )

    return jsonify(notification.serialize()), 200


@notification_blueprint.route("", methods=['GET'])
def get_notifications():
    data = notifications_filter_schema.load(request.args).data

    paginated_notifications = notifications_dao.get_notifications_for_service(
        str(api_user.service_id),
        filter_dict=data,
        key_type=api_user.key_type,
        personalisation=True,
        older_than=data.get('older_than')
    )

    def _build_links(notifications):
        _links = {
            'current': url_for(".get_notifications", **request.args.to_dict(flat=False)),
        }

        if len(notifications):
            next_query_params = dict(request.args.to_dict(flat=False), older_than=notifications[-1].id)
            _links['next'] = url_for(".get_notifications", **next_query_params)

        return _links

    return jsonify(
        notifications=[notification.serialize() for notification in paginated_notifications.items],
        links=_build_links(paginated_notifications.items)
    ), 200
