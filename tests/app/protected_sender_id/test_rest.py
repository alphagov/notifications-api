from app import db
from app.models import ProtectedSenderId


def test_get_check_protected_sender_id(admin_request, notify_db_session):
    data: ProtectedSenderId = ProtectedSenderId(sender_id="famous_company")
    db.session.add(data)
    db.session.commit()

    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        sender_id="famous_company",
    )
    assert response


def test_get_check_unprotected_sender_id(admin_request, notify_db_session):
    data: ProtectedSenderId = ProtectedSenderId(sender_id="famous_company")
    db.session.add(data)
    db.session.commit()

    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        sender_id="government_service",
    )
    assert not response
