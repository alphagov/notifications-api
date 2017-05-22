from urllib.parse import unquote

from flask import Blueprint, current_app, request
from notifications_utils.recipients import normalise_phone_number

from app.dao.services_dao import dao_fetch_services_by_sms_sender
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.models import InboundSms
from app.errors import (
    register_errors,
    InvalidRequest
)

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
    potential_services = dao_fetch_services_by_sms_sender(post_data['Number'])

    if len(potential_services) != 1:
        current_app.logger.error('')
        raise InvalidRequest(
            'Inbound number "{}" not associated with exactly one service'.format(post_data['Number']),
            status_code=400
        )

    service = potential_services[0]

    inbound = create_inbound_sms_object(service, post_data)

    current_app.logger.info('{} received inbound SMS with reference {}'.format(service.id, inbound.provider_reference))

    return 'RECEIVED', 200


def format_message(message):
    return unquote(message.replace('+', ' '))


def create_inbound_sms_object(service, json):
    message = format_message(json['Message'])
    user_number = normalise_phone_number(json['MSISDN'])
    inbound = InboundSms(
        service=service,
        notify_number=service.sms_sender,
        user_number=user_number,
        provider_date=json['DateReceived'],
        provider_reference=json['ID'],
        content=message,
    )
    dao_create_inbound_sms(inbound)
    return inbound
