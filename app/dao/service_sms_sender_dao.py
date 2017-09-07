from app import db
from app.models import ServiceSmsSender


def update_service_sms_sender(service, sms_sender):
    result = db.session.query(
        ServiceSmsSender
    ).filter(
        ServiceSmsSender.service_id == service.id
    ).update(
        {'sms_sender': sms_sender}
    )
    if result == 0:
        new_sms_sender = ServiceSmsSender(sms_sender=sms_sender,
                                          service=service,
                                          is_default=True
                                          )
        db.session.add(new_sms_sender)
        db.session.commit()
