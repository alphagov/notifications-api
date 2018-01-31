import itertools
from datetime import datetime

from flask import (
    jsonify,
    request,
    current_app,
    Blueprint
)
from sqlalchemy.orm.exc import NoResultFound

from app.dao import notifications_dao
from app.dao.dao_utils import dao_rollback
from app.dao.api_key_dao import (
    save_model_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    expire_api_key)
from app.dao.inbound_numbers_dao import dao_allocate_number_for_service
from app.dao.service_sms_sender_dao import (
    dao_add_sms_sender_for_service,
    dao_update_service_sms_sender,
    dao_get_service_sms_senders_by_id,
    dao_get_sms_senders_by_service_id,
    update_existing_sms_sender_with_inbound_number
)
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_archive_service,
    dao_create_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_monthly_historical_stats_for_service,
    dao_fetch_monthly_historical_usage_by_template_for_service,
    dao_fetch_service_by_id,
    dao_fetch_stats_for_service,
    dao_fetch_todays_stats_for_service,
    dao_fetch_todays_stats_for_all_services,
    dao_resume_service,
    dao_remove_user_from_service,
    dao_suspend_service,
    dao_update_service,
    fetch_aggregate_stats_by_date_range_for_all_services,
    fetch_stats_by_date_range_for_all_services
)
from app.dao.service_whitelist_dao import (
    dao_fetch_service_whitelist,
    dao_add_and_commit_whitelisted_contacts,
    dao_remove_service_whitelist
)
from app.dao.service_email_reply_to_dao import (
    add_reply_to_email_address_for_service,
    dao_get_reply_to_by_id,
    dao_get_reply_to_by_service_id,
    update_reply_to_email_address
)
from app.dao.service_letter_contact_dao import (
    dao_get_letter_contacts_by_service_id,
    dao_get_letter_contact_by_id,
    add_letter_contact_for_service,
    update_letter_contact
)
from app.dao.provider_statistics_dao import get_fragment_count
from app.dao.users_dao import get_user_by_id
from app.errors import (
    InvalidRequest,
    register_errors
)
from app.models import Service
from app.schema_validation import validate
from app.service import statistics
from app.service.service_notification_schema import build_notification_for_service
from app.service.service_senders_schema import (
    add_service_email_reply_to_request,
    add_service_letter_contact_block_request,
    add_service_sms_sender_request
)
from app.service.utils import get_whitelist_objects
from app.service.sender import send_notification_to_service_users
from app.service.send_notification import send_one_off_notification
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


@service_blueprint.route('/platform-stats', methods=['GET'])
def get_platform_stats():
    include_from_test_key = request.args.get('include_from_test_key', 'True') != 'False'

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get('start_date', today), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date', today), '%Y-%m-%d').date()
    data = fetch_aggregate_stats_by_date_range_for_all_services(start_date=start_date,
                                                                end_date=end_date,
                                                                include_from_test_key=include_from_test_key
                                                                )
    stats = statistics.format_statistics(data)

    result = jsonify(stats)
    return result


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
        result = jsonify(data=get_detailed_services(start_date=start_date, end_date=end_date,
                                                    only_active=only_active,
                                                    include_from_test_key=include_from_test_key
                                                    ))
        return result
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

    if not data.get('user_id'):
        errors = {'user_id': ['Missing data for required field.']}
        raise InvalidRequest(errors, status_code=400)

    # validate json with marshmallow
    service_schema.load(data)

    user = get_user_by_id(data.pop('user_id'))

    # unpack valid json into service object
    valid_service = Service.from_json(data)

    dao_create_service(valid_service, user)
    return jsonify(data=service_schema.dump(valid_service).data), 201


@service_blueprint.route('/<uuid:service_id>', methods=['POST'])
def update_service(service_id):
    req_json = request.get_json()
    fetched_service = dao_fetch_service_by_id(service_id)
    # Capture the status change here as Marshmallow changes this later
    service_going_live = fetched_service.restricted and not req_json.get('restricted', True)
    current_data = dict(service_schema.dump(fetched_service).data.items())
    current_data.update(request.get_json())

    update_dict = service_schema.load(current_data).data
    org_type = req_json.get('organisation_type', None)
    if org_type:
        update_dict.crown = org_type == 'central'
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
    from app.models import (Service, ApiKey, TemplateHistory)
    from app.schemas import (
        service_history_schema,
        api_key_history_schema,
        template_history_schema
    )

    service_history = Service.get_history_model().query.filter_by(id=service_id).all()
    service_data = service_history_schema.dump(service_history, many=True).data
    api_key_history = ApiKey.get_history_model().query.filter_by(service_id=service_id).all()
    api_keys_data = api_key_history_schema.dump(api_key_history, many=True).data

    template_history = TemplateHistory.query.filter_by(service_id=service_id).all()
    template_data, errors = template_history_schema.dump(template_history, many=True)

    data = {
        'service_history': service_data,
        'api_key_history': api_keys_data,
        'template_history': template_data,
        'events': []}

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


@service_blueprint.route('/<uuid:service_id>/notifications/csv', methods=['GET'])
def get_all_notifications_for_service_csv(service_id):
    data = notifications_filter_schema.load(request.args).data
    if data.get('to'):
        return search_for_notification_by_to_field(service_id, data['to'], statuses=data.get('status'))
    page = data['page'] if 'page' in data else 1
    page_size = data['page_size'] if 'page_size' in data else current_app.config.get('PAGE_SIZE')
    limit_days = data.get('limit_days')
    include_jobs = data.get('include_jobs', True)
    include_from_test_key = data.get('include_from_test_key', False)
    include_created_by_user = data.get('include_created_by_user', False)

    pagination = notifications_dao.get_notifications_for_service(
        service_id,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        include_jobs=include_jobs,
        include_from_test_key=include_from_test_key,
        personalisation=True,
        include_created_by_user=include_created_by_user
    )
    kwargs = request.args.to_dict()
    kwargs['service_id'] = service_id
    results = []
    for n in pagination.items:
        results.append(build_notification_for_service(n))

    return jsonify(
        notifications=results,
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
    if start_date == datetime.utcnow().date():
        stats = dao_fetch_todays_stats_for_all_services(include_from_test_key=include_from_test_key,
                                                        only_active=only_active)
    else:

        stats = fetch_stats_by_date_range_for_all_services(start_date=start_date,
                                                           end_date=end_date,
                                                           include_from_test_key=include_from_test_key,
                                                           only_active=only_active)
    results = []
    for service_id, rows in itertools.groupby(stats, lambda x: x.service_id):
        rows = list(rows)
        if rows[0].count is None:
            s = statistics.create_zeroed_stats_dicts()
        else:
            s = statistics.format_statistics(rows)
        results.append({
            'id': str(rows[0].service_id),
            'name': rows[0].name,
            'notification_type': rows[0].notification_type,
            'research_mode': rows[0].research_mode,
            'restricted': rows[0].restricted,
            'active': rows[0].active,
            'created_at': rows[0].created_at,
            'statistics': s
        })
    return results


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


@service_blueprint.route('/<uuid:service_id>/notifications/templates_usage/monthly', methods=['GET'])
def get_monthly_template_usage(service_id):
    try:
        data = dao_fetch_monthly_historical_usage_by_template_for_service(
            service_id,
            int(request.args.get('year', 'NaN'))
        )

        stats = list()
        for i in data:
            stats.append(
                {
                    'template_id': str(i.template_id),
                    'name': i.name,
                    'type': i.template_type,
                    'month': i.month,
                    'year': i.year,
                    'count': i.count
                }
            )

        return jsonify(stats=stats), 200
    except ValueError:
        raise InvalidRequest('Year must be a number', status_code=400)


@service_blueprint.route('/<uuid:service_id>/send-notification', methods=['POST'])
def create_one_off_notification(service_id):
    resp = send_one_off_notification(service_id, request.get_json())
    return jsonify(resp), 201


@service_blueprint.route('/<uuid:service_id>/email-reply-to', methods=["GET"])
def get_email_reply_to_addresses(service_id):
    result = dao_get_reply_to_by_service_id(service_id)
    return jsonify([i.serialize() for i in result]), 200


@service_blueprint.route('/<uuid:service_id>/email-reply-to/<uuid:reply_to_id>', methods=["GET"])
def get_email_reply_to_address(service_id, reply_to_id):
    result = dao_get_reply_to_by_id(service_id=service_id, reply_to_id=reply_to_id)
    return jsonify(result.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/email-reply-to', methods=['POST'])
def add_service_reply_to_email_address(service_id):
    # validate the service exists, throws ResultNotFound exception.
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_email_reply_to_request)
    new_reply_to = add_reply_to_email_address_for_service(service_id=service_id,
                                                          email_address=form['email_address'],
                                                          is_default=form.get('is_default', True))
    return jsonify(data=new_reply_to.serialize()), 201


@service_blueprint.route('/<uuid:service_id>/email-reply-to/<uuid:reply_to_email_id>', methods=['POST'])
def update_service_reply_to_email_address(service_id, reply_to_email_id):
    # validate the service exists, throws ResultNotFound exception.
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_email_reply_to_request)
    new_reply_to = update_reply_to_email_address(service_id=service_id,
                                                 reply_to_id=reply_to_email_id,
                                                 email_address=form['email_address'],
                                                 is_default=form.get('is_default', True))
    return jsonify(data=new_reply_to.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/letter-contact', methods=["GET"])
def get_letter_contacts(service_id):
    result = dao_get_letter_contacts_by_service_id(service_id)
    return jsonify([i.serialize() for i in result]), 200


@service_blueprint.route('/<uuid:service_id>/letter-contact/<uuid:letter_contact_id>', methods=["GET"])
def get_letter_contact_by_id(service_id, letter_contact_id):
    result = dao_get_letter_contact_by_id(service_id=service_id, letter_contact_id=letter_contact_id)
    return jsonify(result.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/letter-contact', methods=['POST'])
def add_service_letter_contact(service_id):
    # validate the service exists, throws ResultNotFound exception.
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_letter_contact_block_request)
    new_letter_contact = add_letter_contact_for_service(service_id=service_id,
                                                        contact_block=form['contact_block'],
                                                        is_default=form.get('is_default', True))
    return jsonify(data=new_letter_contact.serialize()), 201


@service_blueprint.route('/<uuid:service_id>/letter-contact/<uuid:letter_contact_id>', methods=['POST'])
def update_service_letter_contact(service_id, letter_contact_id):
    # validate the service exists, throws ResultNotFound exception.
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_letter_contact_block_request)
    new_reply_to = update_letter_contact(service_id=service_id,
                                         letter_contact_id=letter_contact_id,
                                         contact_block=form['contact_block'],
                                         is_default=form.get('is_default', True))
    return jsonify(data=new_reply_to.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/sms-sender', methods=['POST'])
def add_service_sms_sender(service_id):
    dao_fetch_service_by_id(service_id)
    form = validate(request.get_json(), add_service_sms_sender_request)
    inbound_number_id = form.get('inbound_number_id', None)
    sms_sender = form.get('sms_sender')

    if inbound_number_id:
        updated_number = dao_allocate_number_for_service(service_id=service_id, inbound_number_id=inbound_number_id)
        # the sms_sender in the form is not set, use the inbound number
        sms_sender = updated_number.number
        existing_sms_sender = dao_get_sms_senders_by_service_id(service_id)
        # we don't want to create a new sms sender for the service if we are allocating an inbound number.
        if len(existing_sms_sender) == 1:
            update_existing_sms_sender = existing_sms_sender[0]
            new_sms_sender = update_existing_sms_sender_with_inbound_number(
                service_sms_sender=update_existing_sms_sender,
                sms_sender=sms_sender,
                inbound_number_id=inbound_number_id)

            return jsonify(new_sms_sender.serialize()), 201

    new_sms_sender = dao_add_sms_sender_for_service(service_id=service_id,
                                                    sms_sender=sms_sender,
                                                    is_default=form['is_default'],
                                                    inbound_number_id=inbound_number_id
                                                    )
    return jsonify(new_sms_sender.serialize()), 201


@service_blueprint.route('/<uuid:service_id>/sms-sender/<uuid:sms_sender_id>', methods=['POST'])
def update_service_sms_sender(service_id, sms_sender_id):
    form = validate(request.get_json(), add_service_sms_sender_request)

    sms_sender_to_update = dao_get_service_sms_senders_by_id(service_id=service_id,
                                                             service_sms_sender_id=sms_sender_id)
    if sms_sender_to_update.inbound_number_id and form['sms_sender'] != sms_sender_to_update.sms_sender:
        raise InvalidRequest("You can not change the inbound number for service {}".format(service_id),
                             status_code=400)

    new_sms_sender = dao_update_service_sms_sender(service_id=service_id,
                                                   service_sms_sender_id=sms_sender_id,
                                                   is_default=form['is_default'],
                                                   sms_sender=form['sms_sender']
                                                   )
    return jsonify(new_sms_sender.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/sms-sender/<uuid:sms_sender_id>', methods=['GET'])
def get_service_sms_sender_by_id(service_id, sms_sender_id):
    sms_sender = dao_get_service_sms_senders_by_id(service_id=service_id,
                                                   service_sms_sender_id=sms_sender_id)
    return jsonify(sms_sender.serialize()), 200


@service_blueprint.route('/<uuid:service_id>/sms-sender', methods=['GET'])
def get_service_sms_senders_for_service(service_id):
    sms_senders = dao_get_sms_senders_by_service_id(service_id=service_id)
    return jsonify([sms_sender.serialize() for sms_sender in sms_senders]), 200


@service_blueprint.route('/unique', methods=["GET"])
def is_service_name_unique():
    name, email_from = check_request_args(request)

    name_exists = Service.query.filter_by(name=name).first()
    email_from_exists = Service.query.filter_by(email_from=email_from).first()
    result = not (name_exists or email_from_exists)
    return jsonify(result=result), 200


def check_request_args(request):
    name = request.args.get('name', None)
    email_from = request.args.get('email_from', None)
    errors = []
    if not name:
        errors.append({'name': ["Can't be empty"]})
    if not email_from:
        errors.append({'email_from': ["Can't be empty"]})
    if errors:
        raise InvalidRequest(errors, status_code=400)
    return name, email_from
