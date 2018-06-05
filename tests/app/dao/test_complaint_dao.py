import uuid

from datetime import datetime

from app.dao.complaint_dao import save_complaint, fetch_complaints_by_service
from app.models import Complaint
from tests.app.db import create_service, create_template, create_notification


def test_fetch_complaint_by_service_returns_one(sample_service, sample_email_notification):
    complaint = Complaint(notification_id=sample_email_notification.id,
                          service_id=sample_service.id,
                          ses_feedback_id=str(uuid.uuid4()),
                          complaint_type='abuse',
                          complaint_date=datetime.utcnow()
                          )

    save_complaint(complaint)

    complaints = fetch_complaints_by_service(service_id=sample_service.id)
    assert len(complaints) == 1
    assert complaints[0] == complaint


def test_fetch_complaint_by_service_returns_empty_list(sample_service):
    complaints = fetch_complaints_by_service(service_id=sample_service.id)
    assert len(complaints) == 0


def test_fetch_complaint_by_service_return_many(notify_db_session):
    service_1 = create_service(service_name='first')
    service_2 = create_service(service_name='second')
    template_1 = create_template(service=service_1, template_type='email')
    template_2 = create_template(service=service_2, template_type='email')
    notification_1 = create_notification(template=template_1)
    notification_2 = create_notification(template=template_2)
    notification_3 = create_notification(template=template_2)
    complaint_1 = Complaint(notification_id=notification_1.id,
                            service_id=service_1.id,
                            ses_feedback_id=str(uuid.uuid4()),
                            complaint_type='abuse',
                            complaint_date=datetime.utcnow()
                            )
    complaint_2 = Complaint(notification_id=notification_2.id,
                            service_id=service_2.id,
                            ses_feedback_id=str(uuid.uuid4()),
                            complaint_type='abuse',
                            complaint_date=datetime.utcnow()
                            )
    complaint_3 = Complaint(notification_id=notification_3.id,
                            service_id=service_2.id,
                            ses_feedback_id=str(uuid.uuid4()),
                            complaint_type='abuse',
                            complaint_date=datetime.utcnow()
                            )

    save_complaint(complaint_1)
    save_complaint(complaint_2)
    save_complaint(complaint_3)

    complaints = fetch_complaints_by_service(service_id=service_2.id)
    assert len(complaints) == 2
    assert complaints[0] == complaint_2
    assert complaints[1] == complaint_3
