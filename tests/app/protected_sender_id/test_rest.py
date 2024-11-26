import uuid

import pytest

from tests.app.db import create_organisation, create_protected_sender_id


@pytest.mark.parametrize(
    "query_params, expected_error_message",
    [
        ({}, "sender_id is a required property"),
        (
            {"sender_id": "famous_company", "organisation_id": "invalid-uuid"},
            "organisation_id badly formed hexadecimal UUID string",
        ),
    ],
    ids=["Missing required field sender_id", "Invalid format for organisation_id"],
)
def test_check_protected_sender_id_validation(admin_request, query_params, expected_error_message):
    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        **query_params,
        _expected_status=400,
    )

    assert any(expected_error_message in error["message"] for error in response["errors"])


def test_get_check_protected_sender_id(admin_request, notify_db_session):
    create_protected_sender_id(sender_id="famous_company")

    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        sender_id="famous_company",
    )
    assert response


def test_get_check_unprotected_sender_id(admin_request, notify_db_session):
    create_protected_sender_id(sender_id="famous_company")

    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        sender_id="government_service",
    )
    assert not response


def test_protected_sender_id_with_matching_organisation(admin_request, notify_db_session):
    organisation_id = str(uuid.uuid4())
    create_organisation(organisation_id=organisation_id, name="org-1")

    create_protected_sender_id(sender_id="famous_company", organisation_id=organisation_id)

    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        sender_id="famous_company",
        organisation_id=organisation_id,
    )

    assert response is True


def test_protected_sender_id_with_non_matching_organisation(admin_request, notify_db_session):
    non_matching_organisation_id = str(uuid.uuid4())
    correct_org = create_organisation(name="default_organisation")

    create_protected_sender_id(sender_id="famous_company", organisation_id=correct_org.id)

    response = admin_request.get(
        "protected-sender-id.check_if_sender_id_is_protected",
        sender_id="famous_company",
        organisation_id=non_matching_organisation_id,
    )

    assert response is False
