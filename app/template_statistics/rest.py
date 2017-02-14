from flask import (
    Blueprint,
    jsonify,
    request,
    current_app)

from app import redis_store
from app.dao.notifications_dao import (
    dao_get_template_usage,
    dao_get_last_template_usage)
from app.dao.templates_dao import dao_get_templates_by_for_cache

from app.schemas import notification_with_template_schema

template_statistics = Blueprint('template-statistics',
                                __name__,
                                url_prefix='/service/<service_id>/template-statistics')

from app.errors import register_errors, InvalidRequest

register_errors(template_statistics)


@template_statistics.route('')
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

    if limit_days == 7:
        stats = get_template_statistics_for_7_days(limit_days, service_id)
    else:
        stats = dao_get_template_usage(service_id, limit_days=limit_days)

    def serialize(data):
        return {
            'count': data.count,
            'template_id': str(data.template_id),
            'template_name': data.name,
            'template_type': data.template_type
        }

    return jsonify(data=[serialize(row) for row in stats])


@template_statistics.route('/<template_id>')
def get_template_statistics_for_template_id(service_id, template_id):
    notification = dao_get_last_template_usage(template_id)
    if not notification:
        message = 'No template found for id {}'.format(template_id)
        errors = {'template_id': [message]}
        raise InvalidRequest(errors, status_code=404)
    data = notification_with_template_schema.dump(notification).data
    return jsonify(data=data)


def get_template_statistics_for_7_days(limit_days, service_id):
    cache_key = "{}-template-counter-limit-7-days".format(service_id)
    template_stats_by_id = redis_store.get_all_from_hash(cache_key)
    if not template_stats_by_id:
        stats = dao_get_template_usage(service_id, limit_days=limit_days)
        cache_values = dict([(x.template_id, x.count) for x in stats])
        redis_store.set_hash_and_expire(cache_key, cache_values, current_app.config.get('EXPIRE_CACHE_IN_SECONDS', 600))
        current_app.logger.info('use redis-client: {}'.format(cache_key))
    else:
        stats = dao_get_templates_by_for_cache(template_stats_by_id.items())
    return stats
