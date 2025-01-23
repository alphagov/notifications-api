import uuid

import pytest

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
