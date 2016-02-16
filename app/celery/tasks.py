from app import notify_celery, twilio_client, db, encryption
from app.clients.sms.twilio import TwilioClientException
from app.dao.templates_dao import get_model_templates
from app.dao.notifications_dao import save_notification
from app.models import Notification
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError


@notify_celery.task(name="send-sms")
def send_sms(service_id, notification_id, encrypted_notification):
    notification = encryption.decrypt(encrypted_notification)
    template = get_model_templates(notification['template'])

    try:
        notification_db_object = Notification(
            id=notification_id,
            template_id=notification['template'],
            to=notification['to'],
            service_id=service_id,
            status='sent'
        )
        save_notification(notification_db_object)

        try:
            twilio_client.send_sms(notification['to'], template.content)
        except TwilioClientException as e:
            current_app.logger.debug(e)
            save_notification(notification_db_object, {"status": "failed"})

    except SQLAlchemyError as e:
        current_app.logger.debug(e)
