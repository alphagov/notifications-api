from datetime import datetime
from typing import Literal
from uuid import UUID

from app import db
from app.constants import (
    SERVICE_JOIN_REQUEST_CANCELLED,
    SERVICE_JOIN_REQUEST_PENDING,
    SERVICE_JOIN_REQUEST_STATUS_TYPES,
)
from app.dao.dao_utils import autocommit
from app.models import ServiceJoinRequest, User


@autocommit
def dao_create_service_join_request(
    requester_id: UUID, service_id: UUID, contacted_user_ids: list[UUID]
) -> ServiceJoinRequest:
    new_request = ServiceJoinRequest(
        requester_id=requester_id,
        service_id=service_id,
    )

    contacted_users = User.query.filter(User.id.in_(contacted_user_ids)).all()
    new_request.contacted_service_users.extend(contacted_users)

    db.session.add(new_request)
    return new_request


def dao_get_service_join_request_by_id(request_id: UUID) -> ServiceJoinRequest | None:
    return (
        ServiceJoinRequest.query.filter_by(id=request_id)
        .options(db.joinedload("contacted_service_users"))
        .one_or_none()
    )


@autocommit
def dao_update_service_join_request(
    request_id: UUID,
    status: Literal[*SERVICE_JOIN_REQUEST_STATUS_TYPES],
    status_changed_by_id: UUID,
    reason: str = None,
) -> ServiceJoinRequest | None:
    service_join_request = dao_get_service_join_request_by_id(request_id)

    if not service_join_request:
        return None

    if status:
        service_join_request.status = status
        service_join_request.status_changed_by_id = status_changed_by_id
        service_join_request.status_changed_at = datetime.utcnow()

    if reason is not None:
        service_join_request.reason = reason

    db.session.add(service_join_request)
    return service_join_request


def dao_cancel_pending_service_join_requests(requester_id: UUID, approver_id: UUID, service_id: UUID) -> None:
    pending_requests = ServiceJoinRequest.query.filter_by(
        requester_id=requester_id, service_id=service_id, status=SERVICE_JOIN_REQUEST_PENDING
    ).all()

    if pending_requests:
        for request in pending_requests:
            dao_update_service_join_request(
                request_id=request.id,
                status=SERVICE_JOIN_REQUEST_CANCELLED,
                status_changed_by_id=approver_id,
                reason="system update due to cancellation",
            )
