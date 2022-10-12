from datetime import datetime

from app.dao.complaint_dao import (
    fetch_count_of_complaints,
    fetch_paginated_complaints,
)
from tests.app.db import create_complaint


def test_fetch_paginated_complaints(mocker, sample_email_notification):
    mocker.patch.dict("app.dao.complaint_dao.current_app.config", {"PAGE_SIZE": 2})
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 1, 1),
    )
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 1, 2),
    )
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 1, 3),
    )

    res = fetch_paginated_complaints(page=1)

    assert len(res.items) == 2
    assert res.items[0].created_at == datetime(2018, 1, 3)
    assert res.items[1].created_at == datetime(2018, 1, 2)

    res = fetch_paginated_complaints(page=2)

    assert len(res.items) == 1
    assert res.items[0].created_at == datetime(2018, 1, 1)


def test_fetch_count_of_complaints(sample_email_notification):
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 6, 6, 22, 00, 00),
    )
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 6, 6, 23, 00, 00),
    )
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 6, 7, 00, 00, 00),
    )
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 6, 7, 13, 00, 00),
    )
    create_complaint(
        service=sample_email_notification.service,
        notification=sample_email_notification,
        created_at=datetime(2018, 6, 7, 23),
    )

    count_of_complaints = fetch_count_of_complaints(start_date=datetime(2018, 6, 7), end_date=datetime(2018, 6, 7))
    assert count_of_complaints == 3


def test_fetch_count_of_complaints_returns_zero(notify_db_session):
    count_of_complaints = fetch_count_of_complaints(start_date=datetime(2018, 6, 7), end_date=datetime(2018, 6, 7))
    assert count_of_complaints == 0
