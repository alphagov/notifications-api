from collections import namedtuple
from uuid import uuid4

import pytest

from app.dao.service_join_requests_dao import dao_create_service_join_request
from tests.app.db import create_service, create_user

ServiceJoinRequestTestCase = namedtuple(
    "TestCase", ["requester_id", "service_id", "contacted_user_ids", "expected_num_contacts"]
)


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
def test_dao_create_service_join_request(client, test_case, notify_db_session):
    create_service(service_id=test_case.service_id, service_name="Service Requester Wants To Join")
    create_user(id=test_case.requester_id, name="Requester User")

    users = []
    for user_id in test_case.contacted_user_ids:
        user = create_user(id=user_id, name=f"User Within Existing Service {user_id}")
        users.append(user)

    request = dao_create_service_join_request(
        requester_id=test_case.requester_id,
        service_id=test_case.service_id,
        contacted_user_ids=test_case.contacted_user_ids,
    )

    assert request.requester_id == test_case.requester_id
    assert request.service_id == test_case.service_id
    assert len(request.contacted_service_users) == test_case.expected_num_contacts

    for user in users:
        assert user in request.contacted_service_users
