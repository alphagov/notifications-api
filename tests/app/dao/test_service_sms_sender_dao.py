from app.dao.service_sms_sender_dao import insert_or_update_service_sms_sender
from app.models import ServiceSmsSender
from tests.app.db import create_service


def test_update_service_sms_sender_updates_existing_row(notify_db_session):
    service = create_service()
    insert_or_update_service_sms_sender(service, 'testing')
    service_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == service.sms_sender

    insert_or_update_service_sms_sender(service, 'NEW_SMS')

    updated_sms_senders = ServiceSmsSender.query.filter_by(service_id=service.id).all()
    assert len(updated_sms_senders) == 1
    assert updated_sms_senders[0].sms_sender == 'NEW_SMS'
    assert updated_sms_senders[0].is_default


def test_create_service_inserts_new_service_sms_sender(notify_db_session):
    assert ServiceSmsSender.query.count() == 0

    service = create_service(sms_sender='new_sms')
    insert_or_update_service_sms_sender(service, 'new_sms')
    service_sms_senders = ServiceSmsSender.query.all()
    assert len(service_sms_senders) == 1
    assert service_sms_senders[0].sms_sender == 'new_sms'
    assert service_sms_senders[0].is_default
