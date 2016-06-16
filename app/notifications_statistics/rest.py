from datetime import (date, timedelta)
from flask import (
    Blueprint,
    jsonify,
    request
)

from app.dao.notifications_dao import (
    dao_get_notification_statistics_for_service,
    dao_get_7_day_agg_notification_statistics_for_service
)
from app.schemas import (
    notifications_statistics_schema,
    week_aggregate_notification_statistics_schema
)

notifications_statistics = Blueprint(
    'notifications-statistics',
    __name__, url_prefix='/service/<service_id>/notifications-statistics'
)

from app.errors import (
    register_errors,
    InvalidRequest
)

register_errors(notifications_statistics)


@notifications_statistics.route('', methods=['GET'])
def get_all_notification_statistics_for_service(service_id):

    if request.args.get('limit_days'):
        try:
            statistics = dao_get_notification_statistics_for_service(
                service_id=service_id,
                limit_days=int(request.args['limit_days'])
            )
        except ValueError as e:
            message = '{} is not an integer'.format(request.args['limit_days'])
            errors = {'limit_days': [message]}
            raise InvalidRequest(errors, status_code=400)
    else:
        statistics = dao_get_notification_statistics_for_service(service_id=service_id)

    data, errors = notifications_statistics_schema.dump(statistics, many=True)
    return jsonify(data=data)


@notifications_statistics.route('/seven_day_aggregate')
def get_notification_statistics_for_service_seven_day_aggregate(service_id):
    data = week_aggregate_notification_statistics_schema.load(request.args).data
    date_from = data['date_from'] if 'date_from' in data else date(date.today().year, 4, 1)
    week_count = data['week_count'] if 'week_count' in data else 52
    stats = dao_get_7_day_agg_notification_statistics_for_service(
        service_id,
        date_from,
        week_count).all()
    json_stats = []
    for x in range(week_count - 1, -1, -1):
        week_stats = stats.pop(0) if len(stats) > 0 and stats[0][0] == x else [x, 0, 0, 0, 0, 0, 0]
        week_start = (date_from + timedelta(days=week_stats[0] * 7))
        if week_start <= date.today():
            json_stats.append({
                'week_start': week_start.strftime('%Y-%m-%d'),
                'week_end': (date_from + timedelta(days=(week_stats[0] * 7) + 6)).strftime('%Y-%m-%d'),
                'emails_requested': week_stats[1],
                'emails_delivered': week_stats[2],
                'emails_failed': week_stats[3],
                'sms_requested': week_stats[4],
                'sms_delivered': week_stats[5],
                'sms_failed': week_stats[6]
            })
    return jsonify(data=json_stats)
