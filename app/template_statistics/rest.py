from flask import (
    Blueprint,
    jsonify,
    request
)

from app.dao.notifications_dao import (
    dao_get_template_usage,
    dao_get_template_statistics_for_service,
    dao_get_template_statistics_for_template
)

from app.schemas import template_statistics_schema

template_statistics = Blueprint('template-statistics',
                                __name__,
                                url_prefix='/service/<service_id>/template-statistics')

from app.errors import register_errors, InvalidRequest

register_errors(template_statistics)


@template_statistics.route('')
def get_template_statistics_for_service(service_id):
    if request.args.get('limit_days'):
        try:
            limit_days = int(request.args['limit_days'])
        except ValueError as e:
            error = '{} is not an integer'.format(request.args['limit_days'])
            message = {'limit_days': [error]}
            raise InvalidRequest(message, status_code=400)
    else:
        limit_days = None
    stats = dao_get_template_statistics_for_service(service_id, limit_days=limit_days)
    data = template_statistics_schema.dump(stats, many=True).data
    return jsonify(data=data)


@template_statistics.route('/replacement')
def get_template_statistics_for_service_by_day(service_id):
    if request.args.get('limit_days'):
        try:
            limit_days = int(request.args['limit_days'])
        except ValueError as e:
            error = '{} is not an integer'.format(request.args['limit_days'])
            message = {'limit_days': [error]}
            raise InvalidRequest(message, status_code=400)
    else:
        limit_days = None
    stats = dao_get_template_usage(service_id, limit_days=limit_days)

    def serialize(row):
        return {
            'count': row.count,
            'day': str(row.day),
            'template_id': str(row.template_id),
            'template_name': row.name,
            'template_type': row.template_type
        }

    return jsonify(data=[serialize(row) for row in stats])


@template_statistics.route('/<template_id>')
def get_template_statistics_for_template_id(service_id, template_id):
    stats = dao_get_template_statistics_for_template(template_id)
    data = template_statistics_schema.dump(stats, many=True).data
    return jsonify(data=data)
