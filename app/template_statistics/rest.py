from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app.dao.notifications_dao import dao_get_template_statistics_for_service

from app.schemas import template_statistics_schema

template_statistics = Blueprint('template-statistics',
                                __name__,
                                url_prefix='/service/<service_id>/template-statistics')

from app.errors import register_errors

register_errors(template_statistics)


@template_statistics.route('')
def get_template_statistics_for_service(service_id):
    if request.args.get('limit_days'):
        try:
            limit_days = int(request.args['limit_days'])
        except ValueError as e:
            error = 'Limit days {} is not an integer'.format(request.args['limit_days'])
            current_app.logger.error(error)
            return jsonify(result="error", message=[error]), 400
    else:
        limit_days = None
    stats = dao_get_template_statistics_for_service(service_id, limit_days=limit_days)
    data, errors = template_statistics_schema.dump(stats, many=True)
    if errors:
        return jsonify(result="error", message=errors), 400
    return jsonify(data=data)
