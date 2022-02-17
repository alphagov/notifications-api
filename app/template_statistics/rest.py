from flask import Blueprint, jsonify, request

from app import redis_store
from app.dao.fact_notification_status_dao import (
    fetch_notification_status_for_service_for_today_and_7_previous_days,
    fetch_notification_status_for_service_for_today_and_7_previous_days_attempt2,
)
from app.dao.notifications_dao import dao_get_last_date_template_was_used
from app.dao.templates_dao import dao_get_template_by_id_and_service_id, dao_get_template_by_id
from app.errors import InvalidRequest, register_errors
from app.utils import DATETIME_FORMAT

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
    data = fetch_notification_status_for_service_for_today_and_7_previous_days_attempt2(
        service_id, by_template=True, limit_days=whole_days
    )

    # service_templates = dao_get_all_templates_for_service(service_id)

    # # for template in service_templates:
    # redis_data = redis_store.get_all_from_hash(f"service-{service_id}:bst-date-2022-02-14:email:sending")
    #     for template_id, value in redis_data:
    #         x = {
    #             'count': value,
    #             'template_id': template_id,
    #             'template_name': row.template_name,
    #             'template_type': notification_type,
    #             'is_precompiled_letter': 
    #             'status': sending
    #         }



    parsed_redis_data = []
    for notification_type in ['email', 'text', 'letter']:
        redis_data = redis_store.get_all_from_hash(f"service-{service_id}:bst-date-2022-02-14:{notification_type}")
        print(redis_data)
        if redis_data:
            for key, value in redis_data.items():
                key = key.decode("utf-8")
                template_id, status = key.split(":")
                print(template_id)
                # print(template_id)
                # print(type(template_id))
                # print('here')
                template_id = template_id.replace("template-", "")
                # print(type(template_id))
                template = dao_get_template_by_id(template_id)
                x = {
                    'count': int(value),
                    'template_id': template_id,
                    'template_name': template.name,
                    'template_type': notification_type,
                    'is_precompiled_letter': False,
                    'status': status
                }
                print(x)
                parsed_redis_data.append(x)


    result = [
        {
            'count': row.count,
            'template_id': str(row.template_id),
            'template_name': row.template_name,
            'template_type': row.notification_type,
            'is_precompiled_letter': row.is_precompiled_letter,
            'status': row.status
        }
        for row in data
    ]

    result = result + parsed_redis_data

    # service-id:xxxxxx-xxxxx:bst-date:2022-02-09:email:template-stats
    #     template-id:yyyyyy-yyyyyy:sending
    #     template-id:yyyyyy-yyyyyy:delivered
    #     template-id:zzzzzz-zzzzzz:sending


    return jsonify(data=result)


@template_statistics.route('/last-used/<uuid:template_id>')
def get_last_used_datetime_for_template(service_id, template_id):
    # Check the template and service exist
    dao_get_template_by_id_and_service_id(template_id, service_id)

    last_date_used = dao_get_last_date_template_was_used(template_id=template_id,
                                                         service_id=service_id)

    return jsonify(last_date_used=last_date_used.strftime(DATETIME_FORMAT) if last_date_used else last_date_used)
