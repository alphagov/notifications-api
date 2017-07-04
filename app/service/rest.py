import itertools
import json
from datetime import datetime

from flask import (
    jsonify,
    request,
    current_app,
    Blueprint
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import NoResultFound

from app import redis_store
from app.dao import notification_usage_dao, notifications_dao
from app.dao.dao_utils import dao_rollback
from app.dao.api_key_dao import (
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    expire_api_key)
from app.dao.date_util import get_financial_year
from app.dao.notification_usage_dao import get_total_billable_units_for_sent_sms_notifications_in_date_range
from app.dao.service_inbound_api_dao import (
    save_service_inbound_api,
    reset_service_inbound_api,
    get_service_inbound_api
)
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
    dao_fetch_todays_stats_for_all_services,
    dao_archive_service,
    fetch_stats_by_date_range_for_all_services,
    dao_suspend_service,
    dao_resume_service,
    dao_fetch_monthly_historical_stats_for_service,
    dao_fetch_monthly_historical_stats_by_template_for_service
)
from app.dao.service_whitelist_dao import (
    dao_fetch_service_whitelist,
    dao_add_and_commit_whitelisted_contacts,
    dao_remove_service_whitelist
)
from app.dao.provider_statistics_dao import get_fragment_count
from app.dao.users_dao import get_user_by_id
from app.errors import (
    InvalidRequest,
    register_errors
)
from app.models import Service, ServiceInboundApi
from app.schema_validation import validate
from app.service import statistics
from app.service.service_inbound_api_schema import service_inbound_api, update_service_inbound_api_schema
from app.service.utils import get_whitelist_objects
from app.service.sender import send_notification_to_service_users
from app.service.send_notification import send_one_off_notification
from app.schemas import (
    service_schema,
    api_key_schema,
    user_schema,
    permission_schema,
    notification_with_template_schema,
    notification_with_personalisation_schema,
    notifications_filter_schema,
    detailed_service_schema
)
from app.utils import pagination_links
from notifications_utils.clients.redis import sms_billable_units_cache_key

service_blueprint = Blueprint('service', __name__)

register_errors(service_blueprint)


@service_blueprint.route('', methods=['GET'])
def get_services():
    only_active = request.args.get('only_active') == 'True'
    detailed = request.args.get('detailed') == 'True'
    user_id = request.args.get('user_id', None)
    include_from_test_key = request.args.get('include_from_test_key', 'True') != 'False'

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get('start_date', today), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date', today), '%Y-%m-%d').date()

    if user_id:
        services = dao_fetch_all_services_by_user(user_id, only_active)
    elif detailed:
        return jsonify(data=get_detailed_services(start_date=start_date, end_date=end_date,
                                                  only_active=only_active, include_from_test_key=include_from_test_key
                                                  ))
    else:
        services = dao_fetch_all_services(only_active)
    data = service_schema.dump(services, many=True).data
    return jsonify(data=data)


@service_blueprint.route('/<uuid:service_id>', methods=['GET'])
def get_service_by_id(service_id):
    if request.args.get('detailed') == 'True':
        data = get_detailed_service(service_id, today_only=request.args.get('today_only') == 'True')
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

    # validate json with marshmallow
    service_schema.load(request.get_json())

    user = get_user_by_id(data.pop('user_id', None))

    # unpack valid json into service object
    valid_service = Service.from_json(data)

    dao_create_service(valid_service, user)
    return jsonify(data=service_schema.dump(valid_service).data), 201


@service_blueprint.route('/<uuid:service_id>', methods=['POST'])
def update_service(service_id):
    fetched_service = dao_fetch_service_by_id(service_id)
    # Capture the status change here as Marshmallow changes this later
    service_going_live = fetched_service.restricted and not request.get_json().get('restricted', True)

    current_data = dict(service_schema.dump(fetched_service).data.items())
    current_data.update(request.get_json())
    update_dict = service_schema.load(current_data).data
    dao_update_service(update_dict)

    if service_going_live:
        send_notification_to_service_users(
            service_id=service_id,
            template_id=current_app.config['SERVICE_NOW_LIVE_TEMPLATE_ID'],
            personalisation={
                'service_name': current_data['name'],
                'message_limit': '{:,}'.format(current_data['message_limit'])
            },
            include_user_fields=['name']
        )

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
    year = request.args.get('year')
    if year is not None:
        try:
            year = int(year)
        except ValueError:
            raise InvalidRequest('Year must be a number', status_code=400)
    return jsonify(data=get_fragment_count(service_id, year=year))


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done
@service_blueprint.route('/<uuid:service_id>/history', methods=['GET'])
def get_service_history(service_id):
    from app.models import (Service, ApiKey, TemplateHistory, Event)
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
    if data.get('to'):
        return search_for_notification_by_to_field(service_id, data['to'], statuses=data.get('status'))
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


@service_blueprint.route('/<uuid:service_id>/notifications/<uuid:notification_id>', methods=['GET'])
def get_notification_for_service(service_id, notification_id):

    notification = notifications_dao.get_notification_with_personalisation(
        service_id,
        notification_id,
        key_type=None,
    )
    return jsonify(
        notification_with_template_schema.dump(notification).data,
    ), 200


def search_for_notification_by_to_field(service_id, search_term, statuses):
    results = notifications_dao.dao_get_notifications_by_to_field(service_id, search_term, statuses)
    return jsonify(
        notifications=notification_with_template_schema.dump(results, many=True).data
    ), 200


@service_blueprint.route('/<uuid:service_id>/notifications/monthly', methods=['GET'])
def get_monthly_notification_stats(service_id):
    service = dao_fetch_service_by_id(service_id)
    try:
        return jsonify(data=dao_fetch_monthly_historical_stats_for_service(
            service.id,
            int(request.args.get('year', 'NaN'))
        ))
    except ValueError:
        raise InvalidRequest('Year must be a number', status_code=400)


def get_detailed_service(service_id, today_only=False):
    service = dao_fetch_service_by_id(service_id)
    stats_fn = dao_fetch_todays_stats_for_service if today_only else dao_fetch_stats_for_service
    stats = stats_fn(service_id)

    service.statistics = statistics.format_statistics(stats)

    return detailed_service_schema.dump(service).data


def get_detailed_services(start_date, end_date, only_active=False, include_from_test_key=True):
    services = {service.id: service for service in dao_fetch_all_services(only_active)}
    if start_date == datetime.utcnow().date():
        stats = dao_fetch_todays_stats_for_all_services(include_from_test_key=include_from_test_key)
    else:

        stats = fetch_stats_by_date_range_for_all_services(start_date=start_date,
                                                           end_date=end_date,
                                                           include_from_test_key=include_from_test_key)

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
        raise InvalidRequest(msg, 400)
    else:
        dao_add_and_commit_whitelisted_contacts(whitelist_objs)
        return '', 204


@service_blueprint.route('/<uuid:service_id>/archive', methods=['POST'])
def archive_service(service_id):
    """
    When a service is archived the service is made inactive, templates are archived and api keys are revoked.
    There is no coming back from this operation.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_archive_service(service.id)

    return '', 204


@service_blueprint.route('/<uuid:service_id>/suspend', methods=['POST'])
def suspend_service(service_id):
    """
    Suspending a service will mark the service as inactive and revoke API keys.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_suspend_service(service.id)

    return '', 204


@service_blueprint.route('/<uuid:service_id>/resume', methods=['POST'])
def resume_service(service_id):
    """
    Resuming a service that has been suspended will mark the service as active.
    The service will need to re-create API keys
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if not service.active:
        dao_resume_service(service.id)

    return '', 204


@service_blueprint.route('/<uuid:service_id>/billable-units')
def get_billable_unit_count(service_id):
    try:
        return jsonify(notifications_dao.get_notification_billable_unit_count_per_month(
            service_id, int(request.args.get('year'))
        ))
    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400


@service_blueprint.route('/<uuid:service_id>/notifications/templates/monthly', methods=['GET'])
def get_monthly_template_stats(service_id):
    service = dao_fetch_service_by_id(service_id)
    try:
        return jsonify(data=dao_fetch_monthly_historical_stats_by_template_for_service(
            service.id,
            int(request.args.get('year', 'NaN'))
        ))
    except ValueError:
        raise InvalidRequest('Year must be a number', status_code=400)


@service_blueprint.route('/<uuid:service_id>/yearly-sms-billable-units')
def get_yearly_sms_billable_units(service_id):
    cache_key = sms_billable_units_cache_key(service_id)
    cached_billable_sms_units = redis_store.get_all_from_hash(cache_key)
    if cached_billable_sms_units:
        return jsonify({
            'billable_sms_units': int(cached_billable_sms_units[b'billable_units']),
            'total_cost': float(cached_billable_sms_units[b'total_cost'])
        })
    else:
        try:
            start_date, end_date = get_financial_year(int(request.args.get('year')))
        except (ValueError, TypeError) as e:
            current_app.logger.exception(e)
            return jsonify(result='error', message='No valid year provided'), 400

        billable_units, total_cost = get_total_billable_units_for_sent_sms_notifications_in_date_range(
            start_date,
            end_date,
            service_id)

        cached_values = {
            'billable_units': billable_units,
            'total_cost': total_cost
        }

        redis_store.set_hash_and_expire(cache_key, cached_values, expire_in_seconds=60)
        return jsonify({
            'billable_sms_units': billable_units,
            'total_cost': total_cost
        })


@service_blueprint.route('/<uuid:service_id>/yearly-usage')
def get_yearly_billing_usage(service_id):
    try:
        year = int(request.args.get('year'))
        results = notification_usage_dao.get_yearly_billing_data(service_id, year)
        json_result = [{"credits": x[0],
                        "billing_units": x[1],
                        "rate_multiplier": x[2],
                        "notification_type": x[3],
                        "international": x[4],
                        "rate": x[5]
                        } for x in results]
        return json.dumps(json_result)

    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400


@service_blueprint.route('/<uuid:service_id>/monthly-usage')
def get_yearly_monthly_usage(service_id):
    try:
        year = int(request.args.get('year'))
        results = notification_usage_dao.get_monthly_billing_data(service_id, year)
        json_results = [{"month": x[0],
                         "billing_units": x[1],
                         "rate_multiplier": x[2],
                         "international": x[3],
                         "notification_type": x[4],
                         "rate": x[5]
                         } for x in results]
        return json.dumps(json_results)
    except TypeError:
        return jsonify(result='error', message='No valid year provided'), 400


@service_blueprint.route('/<uuid:service_id>/inbound-api', methods=['POST'])
def create_service_inbound_api(service_id):
    data = request.get_json()
    validate(data, service_inbound_api)
    data["service_id"] = service_id
    inbound_api = ServiceInboundApi(**data)
    try:
        save_service_inbound_api(inbound_api)
    except SQLAlchemyError as e:
        return handle_sql_errror(e)

    return jsonify(data=inbound_api.serialize()), 201


@service_blueprint.route('/<uuid:service_id>/inbound-api/<uuid:inbound_api_id>', methods=['POST'])
def update_service_inbound_api(service_id, inbound_api_id):
    data = request.get_json()
    validate(data, update_service_inbound_api_schema)

    to_update = get_service_inbound_api(inbound_api_id, service_id)

    reset_service_inbound_api(service_inbound_api=to_update,
                              updated_by_id=data["updated_by_id"],
                              url=data.get("url", None),
                              bearer_token=data.get("bearer_token", None))
    return jsonify(data=to_update.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/inbound-api/<uuid:inbound_api_id>', methods=["GET"])
def fetch_service_inbound_api(service_id, inbound_api_id):
    inbound_api = get_service_inbound_api(inbound_api_id, service_id)

    return jsonify(data=inbound_api.serialize()), 200


def handle_sql_errror(e):
    if hasattr(e, 'orig') and hasattr(e.orig, 'pgerror') and e.orig.pgerror \
            and ('duplicate key value violates unique constraint "ix_service_inbound_api_service_id"'
                 in e.orig.pgerror):
        return jsonify(
            result='error',
            message={'name': ["You can only have one URL and bearer token for your service."]}
        ), 400
    elif hasattr(e, 'orig') and hasattr(e.orig, 'pgerror') and e.orig.pgerror \
            and ('insert or update on table "service_inbound_api" violates '
                 'foreign key constraint "service_inbound_api_service_id_fkey"'
                 in e.orig.pgerror):
        return jsonify(result='error', message="No result found"), 404
    else:
        raise e


@service_blueprint.route('/<uuid:service_id>/send-notification', methods=['POST'])
def create_one_off_notification(service_id):
    resp = send_one_off_notification(service_id, request.get_json())
    return jsonify(resp), 201
