from datetime import date

from flask import (
    jsonify,
    request,
    Blueprint,
    current_app
)
from sqlalchemy.orm.exc import NoResultFound

from app.models import EMAIL_TYPE, SMS_TYPE
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
    dao_fetch_stats_for_service
)
from app.dao import notifications_dao
from app.dao.provider_statistics_dao import get_fragment_count
from app.dao.users_dao import get_model_users
from app.schemas import (
    service_schema,
    api_key_schema,
    user_schema,
    from_to_date_schema,
    permission_schema,
    notification_status_schema,
    notifications_filter_schema,
    detailed_service_schema
)
from app.utils import pagination_links
from app.errors import (
    register_errors,
    InvalidRequest
)

service = Blueprint('service', __name__)
register_errors(service)


@service.route('', methods=['GET'])
def get_services():
    user_id = request.args.get('user_id', None)
    if user_id:
        services = dao_fetch_all_services_by_user(user_id)
    else:
        services = dao_fetch_all_services()
    data = service_schema.dump(services, many=True).data
    return jsonify(data=data)


@service.route('/<uuid:service_id>', methods=['GET'])
def get_service_by_id(service_id):
    if 'detailed' in request.args:
        return get_detailed_service(service_id)
    else:
        fetched = dao_fetch_service_by_id(service_id)

        data = service_schema.dump(fetched).data
        return jsonify(data=data)


@service.route('', methods=['POST'])
def create_service():
    data = request.get_json()
    if not data.get('user_id', None):
        errors = {'user_id': ['Missing data for required field.']}
        raise InvalidRequest(errors, status_code=400)

    user = get_model_users(data['user_id'])
    data.pop('user_id', None)
    valid_service = service_schema.load(request.get_json()).data
    dao_create_service(valid_service, user)
    return jsonify(data=service_schema.dump(valid_service).data), 201


@service.route('/<uuid:service_id>', methods=['POST'])
def update_service(service_id):
    fetched_service = dao_fetch_service_by_id(service_id)
    current_data = dict(service_schema.dump(fetched_service).data.items())
    current_data.update(request.get_json())
    update_dict = service_schema.load(current_data).data
    dao_update_service(update_dict)
    return jsonify(data=service_schema.dump(fetched_service).data), 200


@service.route('/<uuid:service_id>/api-key', methods=['POST'])
def create_api_key(service_id=None):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    valid_api_key = api_key_schema.load(request.get_json()).data
    valid_api_key.service = fetched_service
    save_model_api_key(valid_api_key)
    unsigned_api_key = get_unsigned_secret(valid_api_key.id)
    return jsonify(data=unsigned_api_key), 201


@service.route('/<uuid:service_id>/api-key/revoke/<uuid:api_key_id>', methods=['POST'])
def revoke_api_key(service_id, api_key_id):
    expire_api_key(service_id=service_id, api_key_id=api_key_id)
    return jsonify(), 202


@service.route('/<uuid:service_id>/api-keys', methods=['GET'])
@service.route('/<uuid:service_id>/api-keys/<uuid:key_id>', methods=['GET'])
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


@service.route('/<uuid:service_id>/users', methods=['GET'])
def get_users_for_service(service_id):
    fetched = dao_fetch_service_by_id(service_id)
    result = user_schema.dump(fetched.users, many=True)
    return jsonify(data=result.data)


@service.route('/<uuid:service_id>/users/<user_id>', methods=['POST'])
def add_user_to_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_model_users(user_id=user_id)

    if user in service.users:
        error = 'User id: {} already part of service id: {}'.format(user_id, service_id)
        raise InvalidRequest(error, status_code=400)

    permissions = permission_schema.load(request.get_json(), many=True).data
    dao_add_user_to_service(service, user, permissions)
    data = service_schema.dump(service).data
    return jsonify(data=data), 201


@service.route('/<uuid:service_id>/users/<user_id>', methods=['DELETE'])
def remove_user_from_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_model_users(user_id=user_id)
    if user not in service.users:
        error = 'User not found'
        raise InvalidRequest(error, status_code=404)

    elif len(service.users) == 1:
        error = 'You cannot remove the only user for a service'
        raise InvalidRequest(error, status_code=400)

    dao_remove_user_from_service(service, user)
    return jsonify({}), 204


@service.route('/<uuid:service_id>/fragment/aggregate_statistics')
def get_service_provider_aggregate_statistics(service_id):
    service = dao_fetch_service_by_id(service_id)
    data = from_to_date_schema.load(request.args).data
    return jsonify(data=get_fragment_count(
        service,
        date_from=(data.pop('date_from') if 'date_from' in data else date.today()),
        date_to=(data.pop('date_to') if 'date_to' in data else date.today())
    ))


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done
@service.route('/<uuid:service_id>/history', methods=['GET'])
def get_service_history(service_id):
    from app.models import (Service, ApiKey, Template, Event)
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

    template_history = Template.get_history_model().query.filter_by(service_id=service_id).all()
    template_data, errors = template_history_schema.dump(template_history, many=True)

    events = Event.query.all()
    events_data = event_schema.dump(events, many=True).data

    data = {
        'service_history': service_data,
        'api_key_history': api_keys_data,
        'template_history': template_data,
        'events': events_data}

    return jsonify(data=data)


@service.route('/<uuid:service_id>/notifications', methods=['GET'])
def get_all_notifications_for_service(service_id):
    data = notifications_filter_schema.load(request.args).data
    page = data['page'] if 'page' in data else 1
    page_size = data['page_size'] if 'page_size' in data else current_app.config.get('PAGE_SIZE')
    limit_days = data.get('limit_days')

    pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days)
    kwargs = request.args.to_dict()
    kwargs['service_id'] = service_id
    return jsonify(
        notifications=notification_status_schema.dump(pagination.items, many=True).data,
        page_size=page_size,
        total=pagination.total,
        links=pagination_links(
            pagination,
            '.get_all_notifications_for_service',
            **kwargs
        )
    ), 200


def get_detailed_service(service_id):
    service = dao_fetch_service_by_id(service_id)
    statistics = dao_fetch_stats_for_service(service_id)
    service.statistics = format_statistics(statistics)
    data = detailed_service_schema.dump(service).data
    return jsonify(data=data)


def format_statistics(statistics):
    # statistics come in a named tuple with uniqueness from 'notification_type', 'status' - however missing
    # statuses/notification types won't be represented and the status types need to be simplified/summed up
    # so we can return emails/sms * created, sent, and failed
    counts = {
        template_type: {
            status: 0 for status in ('requested', 'delivered', 'failed')
        } for template_type in (EMAIL_TYPE, SMS_TYPE)
    }
    for row in statistics:
        counts[row.notification_type]['requested'] += row.count
        if row.status == 'delivered':
            counts[row.notification_type]['delivered'] += row.count
        elif row.status in ('failed', 'technical-failure', 'temporary-failure', 'permanent-failure'):
            counts[row.notification_type]['failed'] += row.count

    return counts
