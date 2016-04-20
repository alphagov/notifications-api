from flask import (
    Blueprint,
    jsonify,
    request
)

from app.dao.notifications_dao import (
    dao_get_notification_statistics_for_service,
    dao_get_notification_statistics_for_service_and_previous_days
)
from app.schemas import notifications_statistics_schema

notifications_statistics = Blueprint(
    'notifications-statistics',
    __name__, url_prefix='/service/<service_id>/notifications-statistics'
)

from app.errors import register_errors

register_errors(notifications_statistics)


@notifications_statistics.route('', methods=['GET'])
def get_all_notification_statistics_for_service(service_id):

    if request.args.get('limit_days'):
        try:
            statistics = dao_get_notification_statistics_for_service_and_previous_days(
                service_id=service_id,
                limit_days=int(request.args['limit_days'])
            )
        except ValueError as e:
            error = '{} is not an integer'.format(request.args['limit_days'])
            current_app.logger.error(error)
            return jsonify(result="error", message={'limit_days': [error]}), 400
    else:
        statistics = dao_get_notification_statistics_for_service(service_id=service_id)

    data, errors = notifications_statistics_schema.dump(statistics, many=True)
    return jsonify(data=data)
