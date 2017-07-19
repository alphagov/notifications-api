from urllib.parse import unquote

import iso8601
from flask import jsonify, Blueprint, current_app, request
from notifications_utils.recipients import validate_and_format_phone_number

from app import statsd_client, firetext_client, mmg_client
from app.celery import tasks
from app.config import QueueNames
from app.dao.services_dao import dao_fetch_services_by_sms_sender
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.models import InboundSms, INBOUND_SMS_TYPE, SMS_TYPE
from app.errors import register_errors
from app.utils import convert_bst_to_utc

receive_notifications_blueprint = Blueprint('receive_notifications', __name__)
register_errors(receive_notifications_blueprint)


@receive_notifications_blueprint.route('/notifications/sms/receive/mmg', methods=['POST'])
def receive_mmg_sms():
    """
    {
        'MSISDN': '447123456789'
        'Number': '40604',
        'Message': 'some+uri+encoded+message%3A',
        'ID': 'SOME-MMG-SPECIFIC-ID',
        'DateRecieved': '2017-05-21+11%3A56%3A11'
    }
    """
    post_data = request.get_json()

    inbound_number = strip_leading_forty_four(post_data['Number'])

    potential_services = fetch_potential_services(inbound_number, 'mmg')
    if not potential_services:
        # since this is an issue with our service <-> number mapping, or no inbound_sms service permission
        # we should still tell MMG that we received it successfully
        return 'RECEIVED', 200

    statsd_client.incr('inbound.mmg.successful')

    service = potential_services[0]

    inbound = create_inbound_sms_object(service,
                                        content=format_mmg_message(post_data["Message"]),
                                        from_number=post_data['MSISDN'],
                                        provider_ref=post_data["ID"],
                                        date_received=post_data.get('DateRecieved'),
                                        provider_name="mmg")

    tasks.send_inbound_sms_to_service.apply_async([str(inbound.id), str(service.id)], queue=QueueNames.NOTIFY)

    return 'RECEIVED', 200


@receive_notifications_blueprint.route('/notifications/sms/receive/firetext', methods=['POST'])
def receive_firetext_sms():
    post_data = request.form

    inbound_number = strip_leading_forty_four(post_data['destination'])

    potential_services = fetch_potential_services(inbound_number, 'firetext')
    if not potential_services:
        return jsonify({
            "status": "ok"
        }), 200

    service = potential_services[0]
    inbound = create_inbound_sms_object(service=service,
                                        content=post_data["message"],
                                        from_number=post_data['source'],
                                        provider_ref=None,
                                        date_received=post_data['time'],
                                        provider_name="firetext")

    statsd_client.incr('inbound.firetext.successful')

    tasks.send_inbound_sms_to_service.apply_async([str(inbound.id), str(service.id)], queue=QueueNames.NOTIFY)
    current_app.logger.info(
        '{} received inbound SMS with reference {} from Firetext'.format(service.id, inbound.provider_reference))
    return jsonify({
        "status": "ok"
    }), 200


def format_mmg_message(message):
    return unquote(message.replace('+', ' '))


def format_mmg_datetime(date):
    """
    We expect datetimes in format 2017-05-21+11%3A56%3A11 - ie, spaces replaced with pluses, and URI encoded
    (the same as UTC)
    """
    orig_date = format_mmg_message(date)
    parsed_datetime = iso8601.parse_date(orig_date).replace(tzinfo=None)
    return convert_bst_to_utc(parsed_datetime)


def create_inbound_sms_object(service, content, from_number, provider_ref, date_received, provider_name):
    user_number = validate_and_format_phone_number(from_number, international=True)

    provider_date = date_received
    if provider_date:
        provider_date = format_mmg_datetime(provider_date)

    inbound = InboundSms(
        service=service,
        notify_number=service.sms_sender,
        user_number=user_number,
        provider_date=provider_date,
        provider_reference=provider_ref,
        content=content,
        provider=provider_name
    )
    dao_create_inbound_sms(inbound)
    return inbound


def fetch_potential_services(inbound_number, provider_name):
    potential_services = dao_fetch_services_by_sms_sender(inbound_number)

    if len(potential_services) != 1:
        current_app.logger.error('Inbound number "{}" from {} not associated with exactly one service'.format(
            inbound_number, provider_name
        ))
        statsd_client.incr('inbound.{}.failed'.format(provider_name))
        return False

    if not has_inbound_sms_permissions(potential_services[0].permissions):
        current_app.logger.error(
            'Service "{}" does not allow inbound SMS'.format(potential_services[0].id))
        return False

    return potential_services


def has_inbound_sms_permissions(permissions):
    str_permissions = [p.permission for p in permissions]
    return set([INBOUND_SMS_TYPE, SMS_TYPE]).issubset(set(str_permissions))


def strip_leading_forty_four(number):
    if number.startswith('44'):
        return number.replace('44', '0', 1)
    return number
