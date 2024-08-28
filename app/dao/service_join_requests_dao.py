from uuid import UUID

from app import db
from app.dao.dao_utils import autocommit
from app.models import ServiceJoinRequest, User


@autocommit
def dao_create_service_join_request(
    requester_id: UUID, service_id: UUID, contacted_user_ids: list[UUID] | None = None
) -> ServiceJoinRequest:
    new_request = ServiceJoinRequest(
        requester_id=requester_id,
        service_id=service_id,
    )

    if contacted_user_ids:
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
