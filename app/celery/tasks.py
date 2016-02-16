from itsdangerous import URLSafeSerializer
from app import notify_celery, twilio_client, db
from app.clients.sms.twilio import TwilioClientException
from app.dao.templates_dao import get_model_templates
from app.models import Notification
from flask import current_app


@notify_celery.task(name="send-sms", bind="True")
def send_sms(service_id, notification_id, encrypted_notification, secret_key, salt):
    serializer = URLSafeSerializer(secret_key)

    notification = serializer.loads(encrypted_notification, salt=salt)
    template = get_model_templates(notification['template'])

    status = 'sent'

    try:
        twilio_client.send_sms(notification, template.content)
    except TwilioClientException as e:
        current_app.logger.info(e)
        status = 'failed'

    notification_db_object = Notification(
        id=notification_id,
        template_id=notification['template'],
        to=notification['to'],
        service_id=service_id,
        status=status
    )

    db.session.add(notification_db_object)
    db.session.commit()
