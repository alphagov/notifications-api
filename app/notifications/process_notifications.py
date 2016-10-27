from notifications_utils.renderers import PassThrough
from notifications_utils.template import Template

from app.models import SMS_TYPE
from app.notifications.validators import check_sms_content_char_count
from app.v2.errors import BadRequestError


def create_content_for_notification(template, personalisation):
    template_object = Template(
        template.__dict__,
        personalisation,
        renderer=PassThrough()
    )
    if template_object.missing_data:
        message = 'Missing personalisation: {}'.format(", ".join(template_object.missing_data))
        errors = {'template': [message]}
        raise BadRequestError(errors)

    if template_object.additional_data:
        message = 'Personalisation not needed for template: {}'.format(", ".join(template_object.additional_data))
        errors = {'template': [message]}
        raise BadRequestError(fields=errors)

    if template_object.template_type == SMS_TYPE:
        check_sms_content_char_count(template_object.replaced_content_count)
    return template_object


def persist_notification():
    '''
    persist the notification
    :return:
    '''
    pass


def send_notificaiton_to_queue():
    '''
    send the notification to the queue
    :return:
    '''
    pass
