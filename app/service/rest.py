import itertools

from flask import (
    jsonify,
    request,
    Blueprint,
    current_app
)
from sqlalchemy.orm.exc import NoResultFound

from app.dao.dao_utils import dao_rollback
from app.dao.api_key_dao import (
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    expire_api_key)
from app.dao.services_dao import (
    dao_fetch_service_by_id,
    dao_fetch_all_services,
    dao_create_service,
    dao_update_service,
    dao_fetch_all_services_by_user,
    dao_add_user_to_service,
    dao_remove_user_from_service,
    dao_fetch_stats_for_service,
    dao_fetch_todays_stats_for_service,
    dao_fetch_weekly_historical_stats_for_service,
    dao_fetch_todays_stats_for_all_services
)
from app.dao.service_whitelist_dao import (
    dao_fetch_service_whitelist,
    dao_add_and_commit_whitelisted_contacts,
    dao_remove_service_whitelist
)
from app.dao import notifications_dao
from app.dao.provider_statistics_dao import get_fragment_count
from app.dao.users_dao import get_user_by_id
from app.errors import (
    register_errors,
    InvalidRequest
)
from app.service import statistics
from app.service.utils import get_whitelist_objects
from app.schemas import (
    service_schema,
    api_key_schema,
    user_schema,
    permission_schema,
    notification_with_template_schema,
    notifications_filter_schema,
    detailed_service_schema
)
from app.utils import pagination_links

service_blueprint = Blueprint('service', __name__)
register_errors(service_blueprint)


@service_blueprint.route('', methods=['GET'])
def get_services():
    user_id = request.args.get('user_id', None)
    if user_id:
        services = dao_fetch_all_services_by_user(user_id)
    elif request.args.get('detailed') == 'True':
        return jsonify(data=get_detailed_services())
    else:
        services = dao_fetch_all_services()
    data = service_schema.dump(services, many=True).data
    return jsonify(data=data)


@service_blueprint.route('/<uuid:service_id>', methods=['GET'])
def get_service_by_id(service_id):
    if request.args.get('detailed') == 'True':
        data = get_detailed_service(service_id, today_only=request.args.get('today_only') == 'True')
        return jsonify(data=data)
    else:
        fetched = dao_fetch_service_by_id(service_id)

        data = service_schema.dump(fetched).data
        return jsonify(data=data)


@service_blueprint.route('', methods=['POST'])
def create_service():
    data = request.get_json()
    if not data.get('user_id', None):
        errors = {'user_id': ['Missing data for required field.']}
        raise InvalidRequest(errors, status_code=400)

    user = get_user_by_id(data['user_id'])
    data.pop('user_id', None)
    valid_service = service_schema.load(request.get_json()).data
    dao_create_service(valid_service, user)
    return jsonify(data=service_schema.dump(valid_service).data), 201


@service_blueprint.route('/<uuid:service_id>', methods=['POST'])
def update_service(service_id):
    fetched_service = dao_fetch_service_by_id(service_id)
    current_data = dict(service_schema.dump(fetched_service).data.items())
    current_data.update(request.get_json())
    update_dict = service_schema.load(current_data).data
    dao_update_service(update_dict)
    return jsonify(data=service_schema.dump(fetched_service).data), 200


@service_blueprint.route('/<uuid:service_id>/api-key', methods=['POST'])
def create_api_key(service_id=None):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    valid_api_key = api_key_schema.load(request.get_json()).data
    valid_api_key.service = fetched_service
    save_model_api_key(valid_api_key)
    unsigned_api_key = get_unsigned_secret(valid_api_key.id)
    return jsonify(data=unsigned_api_key), 201


@service_blueprint.route('/<uuid:service_id>/api-key/revoke/<uuid:api_key_id>', methods=['POST'])
def revoke_api_key(service_id, api_key_id):
    expire_api_key(service_id=service_id, api_key_id=api_key_id)
    return jsonify(), 202


@service_blueprint.route('/<uuid:service_id>/api-keys', methods=['GET'])
@service_blueprint.route('/<uuid:service_id>/api-keys/<uuid:key_id>', methods=['GET'])
def get_api_keys(service_id, key_id=None):
    dao_fetch_service_by_id(service_id=service_id)

    try:
        if key_id:
            api_keys = [get_model_api_keys(service_id=service_id, id=key_id)]
        else:
            api_keys = get_model_api_keys(service_id=service_id)
    except NoResultFound:
        error = "API key not found for id: {}".format(service_id)
        raise InvalidRequest(error, status_code=404)

    return jsonify(apiKeys=api_key_schema.dump(api_keys, many=True).data), 200


@service_blueprint.route('/<uuid:service_id>/users', methods=['GET'])
def get_users_for_service(service_id):
    fetched = dao_fetch_service_by_id(service_id)
    result = user_schema.dump(fetched.users, many=True)
    return jsonify(data=result.data)


@service_blueprint.route('/<uuid:service_id>/users/<user_id>', methods=['POST'])
def add_user_to_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)

    if user in service.users:
        error = 'User id: {} already part of service id: {}'.format(user_id, service_id)
        raise InvalidRequest(error, status_code=400)

    permissions = permission_schema.load(request.get_json(), many=True).data
    dao_add_user_to_service(service, user, permissions)
    data = service_schema.dump(service).data
    return jsonify(data=data), 201


@service_blueprint.route('/<uuid:service_id>/users/<user_id>', methods=['DELETE'])
def remove_user_from_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)
    if user not in service.users:
        error = 'User not found'
        raise InvalidRequest(error, status_code=404)

    elif len(service.users) == 1:
        error = 'You cannot remove the only user for a service'
        raise InvalidRequest(error, status_code=400)

    dao_remove_user_from_service(service, user)
    return jsonify({}), 204


@service_blueprint.route('/<uuid:service_id>/fragment/aggregate_statistics')
def get_service_provider_aggregate_statistics(service_id):
    return jsonify(data=get_fragment_count(service_id))


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done
@service_blueprint.route('/<uuid:service_id>/history', methods=['GET'])
def get_service_history(service_id):
    from app.models import (Service, ApiKey, Template, TemplateHistory, Event)
    from app.schemas import (
        service_history_schema,
        api_key_history_schema,
        template_history_schema,
        event_schema
    )

    service_history = Service.get_history_model().query.filter_by(id=service_id).all()
    service_data = service_history_schema.dump(service_history, many=True).data
    api_key_history = ApiKey.get_history_model().query.filter_by(service_id=service_id).all()
    api_keys_data = api_key_history_schema.dump(api_key_history, many=True).data

    template_history = TemplateHistory.query.filter_by(service_id=service_id).all()
    template_data, errors = template_history_schema.dump(template_history, many=True)

    events = Event.query.all()
    events_data = event_schema.dump(events, many=True).data

    data = {
        'service_history': service_data,
        'api_key_history': api_keys_data,
        'template_history': template_data,
        'events': events_data}

    return jsonify(data=data)


@service_blueprint.route('/<uuid:service_id>/notifications', methods=['GET'])
def get_all_notifications_for_service(service_id):
    data = notifications_filter_schema.load(request.args).data
    page = data['page'] if 'page' in data else 1
    page_size = data['page_size'] if 'page_size' in data else current_app.config.get('PAGE_SIZE')
    limit_days = data.get('limit_days')
    include_jobs = data.get('include_jobs', True)
    include_from_test_key = data.get('include_from_test_key', False)

    pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        include_jobs=include_jobs,
        include_from_test_key=include_from_test_key
    )
    kwargs = request.args.to_dict()
    kwargs['service_id'] = service_id
    return jsonify(
        notifications=notification_with_template_schema.dump(pagination.items, many=True).data,
        page_size=page_size,
        total=pagination.total,
        links=pagination_links(
            pagination,
            '.get_all_notifications_for_service',
            **kwargs
        )
    ), 200


@service_blueprint.route('/<uuid:service_id>/notifications/weekly', methods=['GET'])
def get_weekly_notification_stats(service_id):
    service = dao_fetch_service_by_id(service_id)
    stats = dao_fetch_weekly_historical_stats_for_service(service_id)
    stats = statistics.format_weekly_notification_stats(stats, service.created_at)
    return jsonify(data={week.date().isoformat(): statistics for week, statistics in stats.items()})


def get_detailed_service(service_id, today_only=False):
    service = dao_fetch_service_by_id(service_id)
    stats_fn = dao_fetch_todays_stats_for_service if today_only else dao_fetch_stats_for_service
    stats = stats_fn(service_id)

    service.statistics = statistics.format_statistics(stats)

    return detailed_service_schema.dump(service).data


def get_detailed_services():
    services = {service.id: service for service in dao_fetch_all_services()}
    stats = dao_fetch_todays_stats_for_all_services()

    for service_id, rows in itertools.groupby(stats, lambda x: x.service_id):
        services[service_id].statistics = statistics.format_statistics(rows)

    # if service has not sent anything, query will not have set statistics correctly
    for service in services.values():
        if not hasattr(service, 'statistics'):
            service.statistics = statistics.create_zeroed_stats_dicts()

    return detailed_service_schema.dump(services.values(), many=True).data


@service_blueprint.route('/<uuid:service_id>/whitelist', methods=['GET'])
def get_whitelist(service_id):
    from app.models import (EMAIL_TYPE, MOBILE_TYPE)
    service = dao_fetch_service_by_id(service_id)

    if not service:
        raise InvalidRequest("Service does not exist", status_code=404)

    whitelist = dao_fetch_service_whitelist(service.id)
    return jsonify(
        email_addresses=[item.recipient for item in whitelist
                         if item.recipient_type == EMAIL_TYPE],
        phone_numbers=[item.recipient for item in whitelist
                       if item.recipient_type == MOBILE_TYPE]
    )


@service_blueprint.route('/<uuid:service_id>/whitelist', methods=['PUT'])
def update_whitelist(service_id):
    # doesn't commit so if there are any errors, we preserve old values in db
    dao_remove_service_whitelist(service_id)
    try:
        whitelist_objs = get_whitelist_objects(service_id, request.get_json())
    except ValueError as e:
        current_app.logger.exception(e)
        dao_rollback()
        msg = '{} is not a valid email address or phone number'.format(str(e))
        return jsonify(result='error', message=msg), 400
    else:
        dao_add_and_commit_whitelisted_contacts(whitelist_objs)
        return '', 204


@service_blueprint.route('/<uuid:service_id>/billable-units')
def get_billable_unit_count(service_id):
    try:
        return jsonify(notifications_dao.get_notification_billable_unit_count_per_month(
            service_id, int(request.args.get('year'))
        ))
    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400
