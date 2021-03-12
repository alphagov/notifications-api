import uuid
from datetime import datetime, timedelta

from app.dao.complaint_dao import (
    fetch_complaints_by_service,
    fetch_count_of_complaints,
    fetch_paginated_complaints,
    save_complaint,
)
from app.models import Complaint
from tests.app.db import (
    create_complaint,
    create_notification,
    create_service,
    create_template,
)


def test_fetch_paginated_complaints(mocker, sample_email_notification):
    mocker.patch.dict('app.dao.complaint_dao.current_app.config', {'PAGE_SIZE': 2})
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 1, 1))
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 1, 2))
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 1, 3))

    res = fetch_paginated_complaints(page=1)

    assert len(res.items) == 2
    assert res.items[0].created_at == datetime(2018, 1, 3)
    assert res.items[1].created_at == datetime(2018, 1, 2)

    res = fetch_paginated_complaints(page=2)

    assert len(res.items) == 1
    assert res.items[0].created_at == datetime(2018, 1, 1)


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
                            complaint_date=datetime.utcnow(),
                            created_at=datetime.utcnow() + timedelta(minutes=1)
                            )

    save_complaint(complaint_1)
    save_complaint(complaint_2)
    save_complaint(complaint_3)

    complaints = fetch_complaints_by_service(service_id=service_2.id)
    assert len(complaints) == 2
    assert complaints[0] == complaint_3
    assert complaints[1] == complaint_2


def test_fetch_count_of_complaints(sample_email_notification):
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 6, 6, 22, 00, 00))
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 6, 6, 23, 00, 00))
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 6, 7, 00, 00, 00))
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 6, 7, 13, 00, 00))
    create_complaint(service=sample_email_notification.service,
                     notification=sample_email_notification,
                     created_at=datetime(2018, 6, 7, 23))

    count_of_complaints = fetch_count_of_complaints(start_date=datetime(2018, 6, 7),
                                                    end_date=datetime(2018, 6, 7))
    assert count_of_complaints == 3


def test_fetch_count_of_complaints_returns_zero(notify_db):
    count_of_complaints = fetch_count_of_complaints(start_date=datetime(2018, 6, 7),
                                                    end_date=datetime(2018, 6, 7))
    assert count_of_complaints == 0
