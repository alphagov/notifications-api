import datetime
from typing import Any, NotRequired, TypedDict
from uuid import UUID


class SerializedUser(TypedDict):
    id: UUID
    name: str
    email_address: str
    created_at: str
    auth_type: str
    current_session_id: UUID | None
    failed_login_count: int
    email_access_validated_at: str
    logged_in_at: str | None
    mobile_number: str | None
    organisations: list[UUID]
    password_changed_at: str
    permissions: dict[str, list[str]]
    organisation_permissions: dict[str, list[str]]
    platform_admin: bool
    services: list[UUID] | list[dict]
    can_use_webauthn: bool
    state: str
    take_part_in_research: bool
    receives_new_features_email: bool


class SerializedUserForList(TypedDict):
    id: UUID
    name: str
    email_address: str
    mobile_number: str | None


class SerializedEmailBranding(TypedDict):
    id: str
    colour: str | None
    logo: str | None
    name: str
    text: str | None
    brand_type: str
    alt_text: str | None
    created_by: Any | None
    created_at: str | None
    updated_at: str | None


class SerializedLetterBranding(TypedDict):
    id: str
    name: str
    filename: str
    created_by: str | None
    created_at: str | None
    updated_at: str | None


class SerializedOrganisation(TypedDict):
    id: str
    name: str
    active: bool
    crown: bool | None
    organisation_type: str | None
    letter_branding_id: str | None
    email_branding_id: str | None
    agreement_signed: bool | None
    agreement_signed_at: datetime.datetime | None
    agreement_signed_by_id: str | None
    agreement_signed_on_behalf_of_name: str | None
    agreement_signed_on_behalf_of_email_address: str | None
    agreement_signed_version: float | None
    domains: list[str]
    request_to_go_live_notes: str | None
    count_of_live_services: int
    notes: str | None
    purchase_order_number: str | None
    billing_contact_names: str | None
    billing_contact_email_addresses: str | None
    billing_reference: str | None
    can_approve_own_go_live_requests: bool
    permissions: list[str]


class SerializedOrganisationForList(TypedDict):
    name: str
    id: str
    active: bool
    count_of_live_services: int
    domains: list[str]
    organisation_type: str | None


class SerializedServiceOrgDashboard(TypedDict):
    id: str
    name: str
    active: bool
    restricted: bool


class SerializedFreeSmsItems(TypedDict):
    free_sms_fragment_limit: int
    financial_year_start: int


class SerializedService(TypedDict):
    id: str
    name: str


class SerializedAnnualBilling(TypedDict):
    id: str
    free_sms_fragment_limit: int
    service_id: str
    financial_year_start: int
    created_at: str
    updated_at: str | None
    service: SerializedService | None


class SerializedInboundNumber(TypedDict):
    id: str
    number: str
    provider: str
    service: SerializedService | None
    active: bool
    created_at: str
    updated_at: str | None


class SerializedServiceSmsSender(TypedDict):
    id: str
    sms_sender: str
    service_id: str
    is_default: bool
    archived: bool
    inbound_number_id: str | None
    created_at: str
    updated_at: str | None


class SerializedServiceCallbackApi(TypedDict):
    id: str
    service_id: str
    url: str
    updated_by_id: str
    created_at: str
    updated_at: str | None


class SerializedTemplateFolder(TypedDict):
    id: UUID
    name: str
    parent_id: UUID
    service_id: UUID
    users_with_permission: list[str]


class SmsCostDetails(TypedDict):
    billable_sms_fragments: int
    international_rate_multiplier: float
    sms_rate: float


class LetterCostDetails(TypedDict):
    billable_sheets_of_paper: int
    postage: str


class SerializedNotificationForCSV(TypedDict):
    id: UUID
    row_number: str
    recipient: str
    client_reference: str
    template_name: str
    template_type: str
    job_name: str
    status: str
    created_at: str
    created_by_name: str | None
    created_by_email_address: str | None
    api_key_name: str | None


class SerializedNotification(TypedDict):
    id: UUID
    reference: str | None
    email_address: str | None
    phone_number: str | None
    line_1: str | None
    line_2: str | None
    line_3: str | None
    line_4: str | None
    line_5: str | None
    line_6: str | None
    postcode: str | None
    type: str
    status: str
    template: dict
    body: str
    subject: str | None
    created_at: str
    created_by_name: str | None
    sent_at: str | None
    completed_at: str | None
    scheduled_for: None  # Currently hardcoded to None
    postage: str | None
    one_click_unsubscribe_url: str | None
    estimated_delivery: NotRequired[str]


class SerializedNotificationWithCostData(SerializedNotification):
    cost_details: SmsCostDetails | LetterCostDetails | dict
    is_cost_data_ready: bool
    cost_in_pounds: float


class SerializedInvitedOrganisationUser(TypedDict):
    id: str
    email_address: str
    invited_by: str
    organisation: str
    created_at: str
    permissions: list[str]
    status: str


class SerializedRate(TypedDict):
    rate: float
    valid_from: str


class SerializedInboundSms(TypedDict):
    id: str
    created_at: str
    service_id: str
    notify_number: str
    user_number: str
    content: str


class SerializedLetterRate(TypedDict):
    sheet_count: int
    start_date: str
    rate: float
    post_class: str


class SerializedServiceEmailReplyTo(TypedDict):
    id: str
    service_id: str
    email_address: str
    is_default: bool
    archived: bool
    created_at: str
    updated_at: str | None


class SerializedServiceLetterContact(TypedDict):
    id: str
    service_id: str
    contact_block: str
    is_default: bool
    archived: bool
    created_at: str
    updated_at: str | None


class SerializedComplaint(TypedDict):
    id: str
    notification_id: str
    service_id: str
    service_name: str
    ses_feedback_id: str | None
    complaint_type: str | None
    complaint_date: str | None
    created_at: str


class SerializedServiceDataRetention(TypedDict):
    id: str
    service_id: str
    service_name: str
    notification_type: str
    days_of_retention: int
    created_at: str
    updated_at: str | None


class SerializedServiceContactList(TypedDict):
    id: str
    original_file_name: str
    row_count: int
    recent_job_count: int
    has_jobs: bool
    template_type: str
    service_id: str
    created_by: str
    created_at: str


class SerializedWebauthnCredential(TypedDict):
    id: str
    user_id: str
    name: str
    credential_data: str
    created_at: str
    updated_at: str | None
    logged_in_at: str | None


class SerializedLetterAttachment(TypedDict):
    id: str
    created_at: str
    created_by_id: str
    archived_at: str | None
    archived_by_id: str | None
    original_filename: str
    page_count: int


class SerializedUnsubscribeRequestReport(TypedDict):
    batch_id: str | None
    count: int
    created_at: str | None
    earliest_timestamp: str
    latest_timestamp: str
    processed_by_service_at: str | None
    is_a_batched_report: bool
    will_be_archived_at: str
    service_id: str


class SerializedServiceJoinRequest(TypedDict):
    id: str
    service_id: str
    created_at: str
    status: str
    status_changed_at: str | None
    reason: str | None
    contacted_service_users: list[str]
    status_changed_by: Any
    requester: Any


class SerializedReportRequest(TypedDict):
    id: str
    user_id: str
    service_id: str
    report_type: str
    status: str
    parameter: dict
    created_at: str
    updated_at: str | None


class SerializedTemplateEmailFile(TypedDict):
    id: str
    filename: str
    link_text: str
    retention_period: int
    validate_users_email: bool
