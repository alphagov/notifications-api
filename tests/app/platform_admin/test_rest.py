import uuid
from datetime import datetime

import pytest

from app.dao.organisation_dao import dao_add_user_to_organisation
from app.dao.permissions_dao import default_service_permissions
from app.models import (
    ApiKey,
    Complaint,
    EmailBranding,
    InboundNumber,
    InboundSms,
    Job,
    LetterBranding,
    Notification,
    Organisation,
    ProviderDetails,
    Service,
    ServiceCallbackApi,
    ServiceContactList,
    ServiceDataRetention,
    ServiceEmailReplyTo,
    ServiceInboundApi,
    ServiceSmsSender,
    Template,
    TemplateFolder,
    User,
)
from app.platform_admin.rest import (
    FIND_BY_UUID_EXTRA_CONTEXT,
    FIND_BY_UUID_MODELS,
)
from app.utils import DATETIME_FORMAT
from tests.app.db import (
    create_complaint,
    create_email_branding,
    create_inbound_number,
    create_inbound_sms,
    create_letter_branding,
    create_reply_to_email,
    create_service_callback_api,
    create_service_contact_list,
    create_service_data_retention,
    create_service_inbound_api,
    create_service_with_inbound_number,
    create_template_folder,
)


class TestFindByUUID:
    def load_sample_data(self, request, model):  # noqa: C901
        if model == Organisation:
            request.getfixturevalue("sample_organisation")
        elif model == Service:
            request.getfixturevalue("sample_service")
        elif model == Template:
            request.getfixturevalue("sample_template")
        elif model == Notification:
            request.getfixturevalue("sample_notification")
        elif model == EmailBranding:
            create_email_branding()
        elif model == LetterBranding:
            create_letter_branding()
        elif model == User:
            request.getfixturevalue("sample_user")
        elif model == ProviderDetails:
            request.getfixturevalue("sms_providers")
        elif model == ServiceEmailReplyTo:
            sample_service = request.getfixturevalue("sample_service")
            create_reply_to_email(sample_service, "sample_service@notify.test")
        elif model == Job:
            request.getfixturevalue("sample_job")
        elif model == ServiceContactList:
            create_service_contact_list()
        elif model == ServiceDataRetention:
            service = request.getfixturevalue("sample_service")
            create_service_data_retention(service)
        elif model == ServiceSmsSender:
            create_service_with_inbound_number()
        elif model == InboundNumber:
            create_inbound_number("07900900123")
        elif model == ApiKey:
            request.getfixturevalue("sample_api_key")
        elif model == TemplateFolder:
            sample_service = request.getfixturevalue("sample_service")
            create_template_folder(sample_service)
        elif model == ServiceInboundApi:
            sample_service = request.getfixturevalue("sample_service")
            create_service_inbound_api(sample_service)
        elif model == ServiceCallbackApi:
            sample_service = request.getfixturevalue("sample_service")
            create_service_callback_api("delivery_status", sample_service)
        elif model == Complaint:
            create_complaint()
        elif model == InboundSms:
            sample_service = request.getfixturevalue("sample_service")
            create_inbound_sms(sample_service)
        else:
            raise ValueError(model.__name__)

    @pytest.mark.parametrize(
        "model, response_type, context_keys",
        ((value, key, FIND_BY_UUID_EXTRA_CONTEXT.get(key, set())) for key, value in FIND_BY_UUID_MODELS.items()),
    )
    def test_all_known_models(self, request, notify_db_session, admin_request, model, response_type, context_keys):
        self.load_sample_data(request, model)
        notify_db_session.commit()

        (id_,) = notify_db_session.query(model.id).first()

        response = admin_request.post("platform_admin.find_by_uuid", _data={"uuid": str(id_)})

        assert response["type"] == response_type
        assert set(response["context"].keys()) == context_keys

    def test_404_if_no_matches_found(
        self,
        admin_request,
    ):
        admin_request.post("platform_admin.find_by_uuid", _data={"uuid": str(uuid.uuid4())}, _expected_status=404)


@pytest.mark.parametrize(
    "payload, expected_error, expected_status",
    [
        ({}, "{} should be non-empty", 400),
        (
            {"logged_in_start": "invalid-date"},
            "logged_in_start invalid-date is not a date",
            400,
        ),
        (
            {"extra_field": "should_not_be_here"},
            "Additional properties are not allowed (extra_field was unexpected)",
            400,
        ),
        (
            {
                "logged_in_start": None,
                "created_start": None,
                "take_part_in_research": None,
            },
            None,
            200,
        ),
        (
            {
                "logged_in_start": "2024-08-01",
                "created_start": "2023-01-01",
                "take_part_in_research": False,
            },
            None,
            200,
        ),
    ],
)
def test_fetch_users_list_validation_errors(
    client, notify_db_session, admin_request, payload, expected_error, expected_status
):
    response = admin_request.post(
        "platform_admin.fetch_users_list",
        _data=payload,
        _expected_status=expected_status,
    )

    if expected_error is not None:
        assert expected_error in response["errors"][0]["message"]


def test_fetch_users_list_returns_correct_fields(
    admin_request,
    notify_db_session,
    sample_user,
    sample_service,
    sample_organisation,
):
    fixed_date = datetime(2024, 8, 2)
    sample_user.created_at = fixed_date
    sample_user.logged_in_at = fixed_date
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=sample_user.id, permissions=[])

    response = admin_request.post(
        "platform_admin.fetch_users_list",
        _data={
            "logged_in_start": "2024-08-01",
            "created_start": "2023-01-01",
            "take_part_in_research": True,
        },
    )

    users = response["data"]
    user = users[0]

    assert len(users) == 1
    assert user["created_at"] == fixed_date.strftime(DATETIME_FORMAT)
    assert user["permissions"] == {str(sample_service.id): default_service_permissions}
    assert user["take_part_in_research"] is True
    assert user["services"] == [{"id": str(sample_service.id), "name": sample_service.name}]
