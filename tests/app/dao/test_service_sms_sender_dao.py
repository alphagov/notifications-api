from app.dao.service_sms_sender_dao import update_service_sms_sender
from app.models import ServiceSmsSender
from tests.app.db import create_service


def test_update_service_sms_sender_inserts_new_row(notify_db_session):
    service = create_service()

    update_service_sms_sender(service, 'NEW_SMS')

    updated_sms_sender = ServiceSmsSender.query.filter_by(service_id=service.id).one()
    assert updated_sms_sender.sms_sender == 'NEW_SMS'
