from flask import (
    Blueprint,
    jsonify,
)

from app.dao.notifications_dao import (
    dao_get_notification_statistics_for_service
)
from app.schemas import notifications_statistics_schema

notifications_statistics = Blueprint(
    'notifications-statistics',
    __name__, url_prefix='/service/<service_id>/notifications-statistics'
)

from app.errors import register_errors

register_errors(notifications_statistics)


@notifications_statistics.route('', methods=['GET'])
def get_all_templates_for_service(service_id):
    templates = dao_get_notification_statistics_for_service(service_id=service_id)
    data, errors = notifications_statistics_schema.dump(templates, many=True)
    return jsonify(data=data)
