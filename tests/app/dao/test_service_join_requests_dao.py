from collections import namedtuple
from uuid import uuid4

import pytest

from app.constants import JOIN_REQUEST_PENDING
from app.dao.service_join_requests_dao import dao_create_service_join_request, dao_get_service_join_request_by_id
from tests.app.db import create_service, create_user


def setup_service_join_request_test_data(service_id: uuid4(), requester_id: uuid4(), contacted_user_ids: list[uuid4()]):
    """Helper function to create service, requester, and contacted users."""
    create_service(service_id=service_id, service_name=f"Service Requester Wants To Join {service_id}")
    create_user(id=requester_id, name="Requester User")

    users = []
    for user_id in contacted_user_ids:
        user = create_user(id=user_id, name=f"User Within Existing Service {user_id}")
        users.append(user)

    return users


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
    users = setup_service_join_request_test_data(
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
    assert request.status == JOIN_REQUEST_PENDING

    for user in users:
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
    users = setup_service_join_request_test_data(
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
    assert retrieved_request.requester_id == test_case.requester_id
    assert retrieved_request.service_id == test_case.service_id
    assert len(retrieved_request.contacted_service_users) == test_case.expected_num_contacts

    for user in users:
        assert user in retrieved_request.contacted_service_users


def test_get_service_join_request_by_id_not_found(notify_db_session):
    non_existent_id = uuid4()
    retrieved_request = dao_get_service_join_request_by_id(non_existent_id)

    assert retrieved_request is None
