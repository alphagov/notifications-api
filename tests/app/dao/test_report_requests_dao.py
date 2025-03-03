import pytest

from app.constants import (
    REPORT_REQUEST_IN_PROGRESS,
    REPORT_REQUEST_NOTIFICATIONS,
    REPORT_REQUEST_PENDING,
)
from app.dao.report_requests_dao import (
    dao_create_report_request,
    dao_get_report_request_by_id,
)
from app.models import ReportRequest


def test_dao_create_report_request(sample_service, sample_user):
    sample_parameter = {"notification_type": "sms", "notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_IN_PROGRESS,
        parameter=sample_parameter,
    )
    dao_create_report_request(report_request)

    assert report_request.id is not None
    assert report_request.service_id == sample_service.id
    assert report_request.user_id == sample_user.id
    assert report_request.report_type == REPORT_REQUEST_NOTIFICATIONS
    assert report_request.status == REPORT_REQUEST_IN_PROGRESS
    assert report_request.parameter == sample_parameter


def test_dao_create_report_where_not_allowed_additional_property(sample_service, sample_user):
    sample_parameter = {"invalid_type": "invalid", "notification_status": "sending"}

    with pytest.raises(ValueError) as e:
        report_request = ReportRequest(
            user_id=sample_user.id,
            service_id=sample_service.id,
            report_type=REPORT_REQUEST_NOTIFICATIONS,
            status=REPORT_REQUEST_IN_PROGRESS,
            parameter=sample_parameter,
        )
        dao_create_report_request(report_request)

    assert "Invalid parameter: Additional properties are not allowed ('invalid_type' was unexpected)" in str(e.value)


def test_dao_create_report_where_not_valid_notification_type(sample_service, sample_user):
    sample_parameter = {"notification_type": "invalid"}

    with pytest.raises(ValueError) as e:
        report_request = ReportRequest(
            user_id=sample_user.id,
            service_id=sample_service.id,
            report_type=REPORT_REQUEST_NOTIFICATIONS,
            status=REPORT_REQUEST_IN_PROGRESS,
            parameter=sample_parameter,
        )
        dao_create_report_request(report_request)

    assert "Invalid parameter: 'invalid' is not one of ['email', 'sms', 'letter', 'all']" in str(e.value)


def test_dao_create_report_where_not_valid_notification_status(sample_service, sample_user):
    sample_parameter = {"notification_status": "invalid"}

    with pytest.raises(ValueError) as e:
        report_request = ReportRequest(
            user_id=sample_user.id,
            service_id=sample_service.id,
            report_type=REPORT_REQUEST_NOTIFICATIONS,
            status=REPORT_REQUEST_IN_PROGRESS,
            parameter=sample_parameter,
        )
        dao_create_report_request(report_request)

    assert "Invalid parameter: 'invalid' is not one of ['all', 'sending', 'delivered', 'failed']" in str(e.value)


def test_dao_get_report_request_by_id(sample_service, sample_user):
    sample_parameter = {"notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=sample_parameter,
    )

    dao_create_report_request(report_request)
    report = dao_get_report_request_by_id(sample_service.id, report_request.id)

    assert report.id == report_request.id
    assert report.service_id == sample_service.id
    assert report.user_id == sample_user.id
    assert report.report_type == REPORT_REQUEST_NOTIFICATIONS
    assert report.status == REPORT_REQUEST_PENDING
    assert report.parameter == sample_parameter
