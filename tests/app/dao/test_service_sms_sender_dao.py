from app.dao.service_sms_sender_dao import update_service_sms_sender
from app.models import ServiceSmsSender
from tests.app.db import create_service


def test_update_service_sms_sender_updates_existing_row(notify_db_session):
    service = create_service()
    service_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == service.sms_sender

    update_service_sms_sender(service, 'NEW_SMS')

    updated_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(updated_sms_senders) == 1
    assert updated_sms_senders[0].sms_sender == 'NEW_SMS'
