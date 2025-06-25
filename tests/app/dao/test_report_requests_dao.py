from datetime import datetime, timedelta

import pytest
from flask import current_app

from app.constants import (
    REPORT_REQUEST_DELETED,
    REPORT_REQUEST_FAILED,
    REPORT_REQUEST_IN_PROGRESS,
    REPORT_REQUEST_NOTIFICATIONS,
    REPORT_REQUEST_PENDING,
)
from app.dao.report_requests_dao import (
    dao_create_report_request,
    dao_get_active_report_request_by_id,
    dao_get_oldest_ongoing_report_request,
    dao_get_report_request_by_id,
    dao_update_report_request,
)
from app.models import ReportRequest
from tests.app.db import create_report_request


def test_dao_create_report_request(sample_service, sample_user):
    sample_parameter = {"notification_type": "sms", "notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_IN_PROGRESS,
        parameter=sample_parameter,
    )
    result = dao_create_report_request(report_request)

    assert result.id is not None
    assert result.service_id == sample_service.id
    assert result.user_id == sample_user.id
    assert result.report_type == REPORT_REQUEST_NOTIFICATIONS
    assert result.status == REPORT_REQUEST_IN_PROGRESS
    assert result.parameter == sample_parameter


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


@pytest.mark.parametrize("status", [REPORT_REQUEST_PENDING, REPORT_REQUEST_IN_PROGRESS])
def test_dao_get_oldest_ongoing_report_request_returns_true_for_recent_matching_notification_request(
    sample_service, sample_user, status
):
    param = {"notification_type": "sms", "notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=status,
        parameter=param,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        updated_at=datetime.utcnow() - timedelta(minutes=2),
    )
    dao_create_report_request(report_request)
    report_request_notification_timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")

    result = dao_get_oldest_ongoing_report_request(report_request, timeout_minutes=report_request_notification_timeout)
    assert isinstance(result, ReportRequest)


def test_dao_get_oldest_ongoing_report_request_returns_false_for_final_state_notification_request(
    sample_service, sample_user
):
    param = {"notification_type": "sms", "notification_status": "sending"}

    final_status = REPORT_REQUEST_FAILED
    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=final_status,
        parameter=param,
    )
    dao_create_report_request(report_request)
    report_request_notification_timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")

    result = dao_get_oldest_ongoing_report_request(report_request, timeout_minutes=report_request_notification_timeout)
    assert result is None


def test_dao_get_oldest_ongoing_report_request_returns_false_for_stale_updated_at_notification_request(
    sample_service, sample_user
):
    param = {"notification_type": "sms", "notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        updated_at=datetime.utcnow() - timedelta(minutes=45),
    )
    dao_create_report_request(report_request)
    report_request_notification_timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")

    result = dao_get_oldest_ongoing_report_request(report_request, timeout_minutes=report_request_notification_timeout)
    assert result is None


def test_dao_get_oldest_ongoing_report_request_excludes_stale_created_at_when_updated_at_is_none(
    sample_service, sample_user
):
    param = {"notification_type": "sms", "notification_status": "sending"}
    timeout_minutes = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")

    stale_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        created_at=datetime.utcnow() - timedelta(minutes=45),
        updated_at=None,
    )

    fresh_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        updated_at=None,
    )

    dao_create_report_request(stale_request)
    dao_create_report_request(fresh_request)

    result = dao_get_oldest_ongoing_report_request(stale_request, timeout_minutes=timeout_minutes)

    assert result.id == fresh_request.id


def test_dao_get_oldest_ongoing_report_request_returns_none_when_no_match_notification_request(
    sample_service, sample_user
):
    param_existing = {"notification_type": "sms", "notification_status": "sending"}
    param_lookup = {"notification_type": "email", "notification_status": "delivered"}

    existing_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param_existing,
    )
    dao_create_report_request(existing_request)

    lookup_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param_lookup,
    )
    report_request_notification_timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")

    result = dao_get_oldest_ongoing_report_request(lookup_request, timeout_minutes=report_request_notification_timeout)
    assert result is None


def test_dao_get_oldest_ongoing_report_request_returns_true_when_updated_at_is_none_and_created_at_recent(
    sample_service, sample_user
):
    param = {"notification_type": "sms", "notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        updated_at=None,
        created_at=datetime.utcnow() - timedelta(minutes=10),
    )
    dao_create_report_request(report_request)

    timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")
    result = dao_get_oldest_ongoing_report_request(report_request, timeout_minutes=timeout)

    assert isinstance(result, ReportRequest)


def test_dao_get_oldest_ongoing_report_request_returns_true_when_timeout_is_none_even_if_stale(
    sample_service, sample_user
):
    param = {"notification_type": "sms", "notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        updated_at=datetime.utcnow() - timedelta(minutes=999),
    )
    dao_create_report_request(report_request)

    result = dao_get_oldest_ongoing_report_request(report_request)

    assert isinstance(result, ReportRequest)


def test_dao_get_oldest_ongoing_report_request_returns_false_if_user_id_different(
    sample_service, sample_user, notify_user
):
    param = {"notification_type": "sms", "notification_status": "sending"}

    existing = ReportRequest(
        user_id=notify_user.id,  # different user
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
    )
    dao_create_report_request(existing)

    lookup = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
    )

    timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")
    assert dao_get_oldest_ongoing_report_request(lookup, timeout_minutes=timeout) is None


def test_dao_get_oldest_ongoing_report_request_returns_oldest_when_multiple_matches_exist(sample_service, sample_user):
    param = {"notification_type": "sms", "notification_status": "sending"}

    newer_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        created_at=datetime.utcnow() - timedelta(minutes=5),
        updated_at=datetime.utcnow() - timedelta(minutes=2),
    )
    older_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_PENDING,
        parameter=param,
        created_at=datetime.utcnow() - timedelta(minutes=15),
        updated_at=datetime.utcnow() - timedelta(minutes=10),
    )

    dao_create_report_request(newer_request)
    dao_create_report_request(older_request)

    timeout = current_app.config.get("REPORT_REQUEST_NOTIFICATIONS_TIMEOUT_MINUTES")
    result = dao_get_oldest_ongoing_report_request(older_request, timeout_minutes=timeout)

    assert isinstance(result, ReportRequest)
    assert result.id == older_request.id


def test_dao_update_report_request(sample_service, sample_user):
    report_request = create_report_request(sample_user.id, sample_service.id)

    assert report_request.status == REPORT_REQUEST_PENDING
    assert not report_request.updated_at

    report_request.status = REPORT_REQUEST_IN_PROGRESS
    dao_update_report_request(report_request)

    assert report_request.status == REPORT_REQUEST_IN_PROGRESS
    assert report_request.updated_at


def test_dao_get_active_report_request_by_id_when_deleted_report(sample_service, sample_user):
    sample_parameter = {"notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_DELETED,
        parameter=sample_parameter,
    )

    dao_create_report_request(report_request)

    report = dao_get_active_report_request_by_id(sample_service.id, report_request.id)
    assert report is None


def test_dao_get_active_report_request_by_id_when_active_report(sample_service, sample_user):
    sample_parameter = {"notification_status": "sending"}

    report_request = ReportRequest(
        user_id=sample_user.id,
        service_id=sample_service.id,
        report_type=REPORT_REQUEST_NOTIFICATIONS,
        status=REPORT_REQUEST_IN_PROGRESS,
        parameter=sample_parameter,
    )

    dao_create_report_request(report_request)
    report = dao_get_report_request_by_id(sample_service.id, report_request.id)

    assert report.id == report_request.id
    assert report.service_id == sample_service.id
    assert report.user_id == sample_user.id
    assert report.report_type == REPORT_REQUEST_NOTIFICATIONS
    assert report.status == REPORT_REQUEST_IN_PROGRESS
    assert report.parameter == sample_parameter
