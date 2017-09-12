from app import db
from app.dao.dao_utils import transactional
from app.models import ServiceSmsSender


@transactional
def insert_or_update_service_sms_sender(service, sms_sender, inbound_number_id=None):
    result = db.session.query(
        ServiceSmsSender
    ).filter(
        ServiceSmsSender.service_id == service.id
    ).update(
        {'sms_sender': sms_sender,
         'inbound_number_id': inbound_number_id
         }
    )
    if result == 0:
        new_sms_sender = ServiceSmsSender(sms_sender=sms_sender,
                                          service=service,
                                          is_default=True,
                                          inbound_number_id=inbound_number_id
                                          )
        db.session.add(new_sms_sender)


def insert_service_sms_sender(service, sms_sender):
    """
    This method is called from create_service which is wrapped in a transaction.
    """
    new_sms_sender = ServiceSmsSender(sms_sender=sms_sender,
                                      service=service,
                                      is_default=True
                                      )
    db.session.add(new_sms_sender)
