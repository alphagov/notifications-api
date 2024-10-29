from collections import namedtuple
from uuid import uuid4

import pytest

from app.constants import (
    SERVICE_JOIN_REQUEST_APPROVED,
    SERVICE_JOIN_REQUEST_CANCELLED,
    SERVICE_JOIN_REQUEST_PENDING,
    SERVICE_JOIN_REQUEST_REJECTED,
)
from app.dao.service_join_requests_dao import (
    dao_cancel_pending_service_join_requests,
    dao_create_service_join_request,
    dao_get_service_join_request_by_id,
    dao_update_service_join_request,
)
from app.models import ServiceJoinRequest, User
from tests.app.db import create_service, create_user


def setup_service_join_request_test_data(
    service_id: uuid4(), requester_id: uuid4(), contacted_user_ids: list[uuid4()]
) -> tuple[User, list[User]]:
    """Helper function to create service, requester, and contacted users."""
    create_service(service_id=service_id, service_name=f"Service Requester Wants To Join {service_id}")
    create_user(id=requester_id, name="Requester User", email=f"{requester_id}@digital.cabinet-office.gov.uk")

    contacted_users = []
    for user_id in contacted_user_ids:
        user = create_user(
            id=user_id,
            name=f"User Within Existing Service {user_id}",
            email=f"{user_id}@digital.cabinet-office.gov.uk",
        )
        contacted_users.append(user)

    return contacted_users


def create_service_join_request(requester_id, service_id, contacted_user_ids, status=None, decider_id=None):
    """Helper function to create a service join request and optionally update its status."""
    service_join_request = dao_create_service_join_request(
        requester_id=requester_id,
        service_id=service_id,
        contacted_user_ids=contacted_user_ids,
    )

    if status and decider_id:
        service_join_request = dao_update_service_join_request(
            request_id=service_join_request.id,
            status=status,
            status_changed_by_id=decider_id,
        )

    return service_join_request


ServiceJoinRequestTestCase = namedtuple(
    "TestCase", ["requester_id", "service_id", "contacted_user_ids", "expected_num_contacts"]
)


@pytest.mark.parametrize(
    "test_case",
    [
        ServiceJoinRequestTestCase(
            requester_id=uuid4(),
            service_id=uuid4(),
            contacted_user_ids=[uuid4(), uuid4()],
            expected_num_contacts=2,
        ),
        ServiceJoinRequestTestCase(
            requester_id=uuid4(),
            service_id=uuid4(),
            contacted_user_ids=[uuid4()],
            expected_num_contacts=1,
        ),
    ],
    ids=["two_contacts", "one_contact"],
)
def test_dao_create_service_join_request(client, test_case, notify_db_session):
    contacted_users = setup_service_join_request_test_data(
        test_case.service_id, test_case.requester_id, test_case.contacted_user_ids
    )

    request = dao_create_service_join_request(
        requester_id=test_case.requester_id,
        service_id=test_case.service_id,
        contacted_user_ids=test_case.contacted_user_ids,
    )

    assert request.requester_id == test_case.requester_id
    assert request.service_id == test_case.service_id
    assert len(request.contacted_service_users) == test_case.expected_num_contacts
    assert request.status == SERVICE_JOIN_REQUEST_PENDING

    for user in contacted_users:
        assert user in request.contacted_service_users


@pytest.mark.parametrize(
    "test_case",
    [
        ServiceJoinRequestTestCase(
            requester_id=uuid4(),
            service_id=uuid4(),
            contacted_user_ids=[],
            expected_num_contacts=0,
        ),
        ServiceJoinRequestTestCase(
            requester_id=uuid4(),
            service_id=uuid4(),
            contacted_user_ids=[uuid4(), uuid4()],
            expected_num_contacts=2,
        ),
        ServiceJoinRequestTestCase(
            requester_id=uuid4(),
            service_id=uuid4(),
            contacted_user_ids=[uuid4()],
            expected_num_contacts=1,
        ),
    ],
    ids=["no_contacts", "two_contacts", "one_contact"],
)
def test_get_service_join_request_by_id(client, test_case, notify_db_session):
    contacted_user = setup_service_join_request_test_data(
        test_case.service_id, test_case.requester_id, test_case.contacted_user_ids
    )

    request = dao_create_service_join_request(
        requester_id=test_case.requester_id,
        service_id=test_case.service_id,
        contacted_user_ids=test_case.contacted_user_ids,
    )

    retrieved_request = dao_get_service_join_request_by_id(request.id)

    assert retrieved_request is not None
    assert retrieved_request.id == request.id
    assert retrieved_request.requester.id == test_case.requester_id
    assert retrieved_request.service_id == test_case.service_id
    assert len(retrieved_request.contacted_service_users) == test_case.expected_num_contacts

    for user in contacted_user:
        assert user in retrieved_request.contacted_service_users


def test_get_service_join_request_by_id_not_found(notify_db_session):
    non_existent_id = uuid4()
    retrieved_request = dao_get_service_join_request_by_id(non_existent_id)

    assert retrieved_request is None


@pytest.mark.parametrize(
    "updated_status,reason",
    [
        (SERVICE_JOIN_REQUEST_APPROVED, None),
        (SERVICE_JOIN_REQUEST_REJECTED, "Rejected due to incomplete information"),
    ],
    ids=["Approved", "Rejected with reason"],
)
def test_dao_update_service_join_request(client, notify_db_session, updated_status, reason):
    requester_id = uuid4()
    service_id = uuid4()
    user_1 = uuid4()
    user_2 = uuid4()

    setup_service_join_request_test_data(service_id, requester_id, [user_1, user_2])

    request = dao_create_service_join_request(
        requester_id=requester_id,
        service_id=service_id,
        contacted_user_ids=[user_1, user_2],
    )

    updated_request = dao_update_service_join_request(
        request_id=request.id,
        status=updated_status,
        status_changed_by_id=user_1,
        reason=reason,
    )

    assert updated_request.status == updated_status
    assert updated_request.status_changed_by_id == user_1
    assert updated_request.reason == reason
    assert len(updated_request.contacted_service_users) == 2


def test_dao_update_service_join_request_no_request_found(client, notify_db_session):
    requester_id = uuid4()
    request_id = uuid4()
    service_id = uuid4()
    user_1 = uuid4()

    setup_service_join_request_test_data(service_id, requester_id, [user_1])

    updated_request = dao_update_service_join_request(
        request_id=request_id,
        status=SERVICE_JOIN_REQUEST_REJECTED,
        status_changed_by_id=user_1,
        reason=None,
    )

    assert updated_request is None


def test_dao_cancel_pending_service_join_requests(client, notify_db_session):
    requester_id = uuid4()
    decider_id = uuid4()
    service_id = uuid4()

    setup_service_join_request_test_data(service_id, requester_id, [decider_id])

    pending_request_1 = create_service_join_request(
        requester_id, service_id, [decider_id], status=SERVICE_JOIN_REQUEST_REJECTED, decider_id=decider_id
    )

    pending_request_2 = create_service_join_request(requester_id, service_id, [decider_id])

    pending_request_3 = create_service_join_request(requester_id, service_id, [decider_id])

    pending_request_4 = create_service_join_request(
        requester_id, service_id, [decider_id], status=SERVICE_JOIN_REQUEST_APPROVED, decider_id=decider_id
    )

    dao_cancel_pending_service_join_requests(requester_id, decider_id, service_id)

    all_user_requests = ServiceJoinRequest.query.filter_by(service_id=service_id, requester_id=requester_id).all()

    request_status_map = {request.id: request.status for request in all_user_requests}
    request_reason_map = {request.id: request.reason for request in all_user_requests}

    assert len(all_user_requests) == 4

    assert request_status_map[pending_request_1.id] == SERVICE_JOIN_REQUEST_REJECTED
    assert request_status_map[pending_request_4.id] == SERVICE_JOIN_REQUEST_APPROVED

    assert request_status_map[pending_request_2.id] == SERVICE_JOIN_REQUEST_CANCELLED
    assert request_status_map[pending_request_3.id] == SERVICE_JOIN_REQUEST_CANCELLED

    assert request_reason_map[pending_request_1.id] is None
    assert request_reason_map[pending_request_4.id] is None
    assert request_reason_map[pending_request_2.id] == "system update due to cancellation"
    assert request_reason_map[pending_request_3.id] == "system update due to cancellation"


def test_dao_cancel_pending_service_join_requests_no_pending_requests(client, notify_db_session):
    requester_id = uuid4()
    decider_id = uuid4()
    service_id = uuid4()

    setup_service_join_request_test_data(service_id, requester_id, [decider_id])

    approved_request = create_service_join_request(
        requester_id, service_id, [decider_id], status=SERVICE_JOIN_REQUEST_APPROVED, decider_id=decider_id
    )

    rejected_request = create_service_join_request(
        requester_id, service_id, [decider_id], status=SERVICE_JOIN_REQUEST_REJECTED, decider_id=decider_id
    )

    dao_cancel_pending_service_join_requests(requester_id, decider_id, service_id)

    all_user_requests = ServiceJoinRequest.query.filter_by(service_id=service_id, requester_id=requester_id).all()

    request_status_map = {request.id: request.status for request in all_user_requests}

    assert len(all_user_requests) == 2
    assert request_status_map[approved_request.id] == SERVICE_JOIN_REQUEST_APPROVED
    assert request_status_map[rejected_request.id] == SERVICE_JOIN_REQUEST_REJECTED


def test_dao_cancel_pending_service_join_requests_service_specific(client, notify_db_session):
    requester_id = uuid4()
    decider_id = uuid4()
    service_id_1 = uuid4()
    service_id_2 = uuid4()

    setup_service_join_request_test_data(service_id_1, requester_id, [decider_id])
    setup_service_join_request_test_data(service_id_2, requester_id, [decider_id])

    pending_request_service_1_1 = create_service_join_request(requester_id, service_id_1, [decider_id])
    pending_request_service_1_2 = create_service_join_request(requester_id, service_id_1, [decider_id])

    pending_request_service_2 = create_service_join_request(requester_id, service_id_2, [decider_id])
    approved_request_service_2 = create_service_join_request(
        requester_id, service_id_2, [decider_id], status=SERVICE_JOIN_REQUEST_APPROVED, decider_id=decider_id
    )

    # Cancel pending requests for service 1 only
    dao_cancel_pending_service_join_requests(requester_id, decider_id, service_id_1)

    all_user_requests_service_1 = ServiceJoinRequest.query.filter_by(
        service_id=service_id_1, requester_id=requester_id
    ).all()

    all_user_requests_service_2 = ServiceJoinRequest.query.filter_by(
        service_id=service_id_2, requester_id=requester_id
    ).all()

    request_status_map_service_1 = {request.id: request.status for request in all_user_requests_service_1}
    request_status_map_service_2 = {request.id: request.status for request in all_user_requests_service_2}

    # Verify that pending requests for service 1 were canceled
    assert request_status_map_service_1[pending_request_service_1_1.id] == SERVICE_JOIN_REQUEST_CANCELLED
    assert request_status_map_service_1[pending_request_service_1_2.id] == SERVICE_JOIN_REQUEST_CANCELLED

    # Verify that the pending request for service 2 remains pending
    assert request_status_map_service_2[pending_request_service_2.id] == SERVICE_JOIN_REQUEST_PENDING

    # Verify that the approved request for service 2 remains approved
    assert request_status_map_service_2[approved_request_service_2.id] == SERVICE_JOIN_REQUEST_APPROVED
