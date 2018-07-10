from flask import (
    Blueprint,
    jsonify,
    request,
    current_app
)

from app import redis_store
from app.dao.notifications_dao import (
    dao_get_template_usage,
    dao_get_last_template_usage
)
from app.dao.templates_dao import (
    dao_get_multiple_template_details,
    dao_get_template_by_id_and_service_id
)

from app.schemas import notification_with_template_schema
from app.utils import cache_key_for_service_template_usage_per_day, last_n_days
from app.errors import register_errors, InvalidRequest
from collections import Counter

template_statistics = Blueprint('template_statistics',
                                __name__,
                                url_prefix='/service/<service_id>/template-statistics')

register_errors(template_statistics)


@template_statistics.route('')
def get_template_statistics_for_service_by_day(service_id):
    whole_days = request.args.get('whole_days', request.args.get('limit_days', ''))
    try:
        whole_days = int(whole_days)
    except ValueError:
        error = '{} is not an integer'.format(whole_days)
        message = {'whole_days': [error]}
        raise InvalidRequest(message, status_code=400)

    if whole_days < 0 or whole_days > 7:
        raise InvalidRequest({'whole_days': ['whole_days must be between 0 and 7']}, status_code=400)

    return jsonify(data=_get_template_statistics_for_last_n_days(service_id, whole_days))


@template_statistics.route('/<template_id>')
def get_template_statistics_for_template_id(service_id, template_id):
    template = dao_get_template_by_id_and_service_id(template_id, service_id)

    data = None
    notification = dao_get_last_template_usage(template_id, template.template_type, template.service_id)
    if notification:
        data = notification_with_template_schema.dump(notification).data

    return jsonify(data=data)


def _get_template_statistics_for_last_n_days(service_id, whole_days):
    template_stats_by_id = Counter()

    # 0 whole_days = last 1 days (ie since midnight today) = today.
    # 7 whole days = last 8 days (ie since midnight this day last week) = a week and a bit
    for day in last_n_days(whole_days + 1):
        # "{SERVICE_ID}-template-usage-{YYYY-MM-DD}"
        key = cache_key_for_service_template_usage_per_day(service_id, day)
        stats = redis_store.get_all_from_hash(key)
        if stats:
            stats = {
                k.decode('utf-8'): int(v) for k, v in stats.items()
            }
        else:
            # key didn't exist (or redis was down) - lets populate from DB.
            stats = {
                str(row.id): row.count for row in dao_get_template_usage(service_id, day=day)
            }
            # if there is data in db, but not in redis - lets put it in redis so we don't have to do
            # this calc again next time. If there isn't any data, we can't put it in redis.
            # Zero length hashes aren't a thing in redis. (There'll only be no data if the service has no templates)
            # Nothing is stored if redis is down.
            if stats:
                redis_store.set_hash_and_expire(
                    key,
                    stats,
                    current_app.config['EXPIRE_CACHE_EIGHT_DAYS']
                )
        template_stats_by_id += Counter(stats)

    # attach count from stats to name/type/etc from database
    template_details = dao_get_multiple_template_details(template_stats_by_id.keys())
    return [
        {
            'count': template_stats_by_id[str(template.id)],
            'template_id': str(template.id),
            'template_name': template.name,
            'template_type': template.template_type,
            'is_precompiled_letter': template.is_precompiled_letter
        }
        for template in template_details
        # we don't want to return templates with no count to the front-end,
        # but they're returned from the DB and might be put in redis like that (if there was no data that day)
        if template_stats_by_id[str(template.id)] != 0
    ]
