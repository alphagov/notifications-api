from typing import Any, TypedDict
from dataclasses import dataclass
import datetime

@dataclass
class SerializedUser:
    id: str
    name: str
    email_address: str
    created_at: str
    auth_type: str
    current_session_id: str | None
    failed_login_count: int
    email_access_validated_at: str
    logged_in_at: str | None
    mobile_number: str | None
    organisations: list[str]
    password_changed_at: str
    permissions: dict[str, list[str]]
    organisation_permissions: dict[str, list[str]]
    platform_admin: bool
    services: list[str] | list[dict]
    can_use_webauthn: bool
    state: str
    take_part_in_research: bool
    receives_new_features_email: bool

    def __iter__(self):
        # Return an iterator of the instance's attributes as (key, value) pairs
        return iter(self.__dict__.items())


@dataclass
class SerializedUserForList:
    id: str
    name: str
    email_address: str
    mobile_number: str | None


@dataclass
class SerializedEmailBranding:
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

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


@dataclass
class SerializedLetterBranding:
    id: str
    name: str
    filename: str
    created_by: str | None
    created_at: str | None
    updated_at: str | None


@dataclass
class SerializedOrganisation:
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


@dataclass
class SerializedOrganisationForList:
    name: str
    id: str
    active: bool
    count_of_live_services: int
    domains: list[str]
    organisation_type: str | None


@dataclass
class SerializedServiceOrgDashboard:
    id: str
    name: str
    active: bool
    restricted: bool


@dataclass
class SerializedFreeSmsItems:
    free_sms_fragment_limit: int
    financial_year_start: int


@dataclass
class SeralizedService:
    id: str
    name: str


@dataclass
class SerializedAnnualBilling:
    id: str
    free_sms_fragment_limit: int
    service_id: str
    financial_year_start: int
    created_at: str
    updated_at: str | None
    service: SeralizedService | None


@dataclass
class SerializedInboundNumber:
    id: str
    number: str
    provider: str
    service: SeralizedService | None
    active: bool
    created_at: str
    updated_at: str | None

    def get(self, key: str, default=None):
        return getattr(self, key, default)


@dataclass
class SerializedServiceSmsSender:
    id: str
    sms_sender: str
    service_id: str
    is_default: bool
    archived: bool
    inbound_number_id: str | None
    created_at: str
    updated_at: str | None


@dataclass
class SerializedServiceCallbackApi:
    id: str
    service_id: str
    url: str
    updated_by_id: str
    created_at: str
    updated_at: str | None


@dataclass
class SerializedTemplateFolder:
    id: str
    name: str
    parent_id: str | None
    service_id: str
    users_with_permission: list[str]


@dataclass
class SmsCostDetails:
    billable_sms_fragments: int
    international_rate_multiplier: float
    sms_rate: float


@dataclass
class LetterCostDetails:
    billable_sheets_of_paper: int
    postage: str


@dataclass
class SerializedNotificationForCSV:
    id: str
    row_number: str
    recipient: str
    client_reference: str
    template_name: str
    template_type: str
    job_name: str
    status: str
    created_at: str
    created_by_name: str
    created_by_email_address: str
    api_key_name: str | None

    def __getitem__(self, key):
        return getattr(self, key)


@dataclass
class SerializedNotification:
    id: str
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
    scheduled_for: str | None
    postage: str | None
    one_click_unsubscribe_url: str | None
    estimated_delivery: str | None
    cost_details: SmsCostDetails | LetterCostDetails | dict | None = None
    cost_in_pounds: float | None = None
    is_cost_data_ready: bool | None = None

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


@dataclass
class SerializedInvitedOrganisationUser:
    id: str
    email_address: str
    invited_by: str
    organisation: str
    created_at: str
    permissions: list[str]
    status: str


@dataclass
class SerializedRate:
    rate: float
    valid_from: str


@dataclass
class SerializedInboundSms:
    id: str
    created_at: str
    service_id: str
    notify_number: str
    user_number: str
    content: str


@dataclass
class SerializedLetterRate:
    sheet_count: int
    start_date: str
    rate: str
    post_class: str


@dataclass
class SerializedServiceEmailReplyTo:
    id: str
    service_id: str
    email_address: str
    is_default: bool
    archived: bool
    created_at: str
    updated_at: str | None


@dataclass
class SerializedServiceLetterContact:
    id: str
    service_id: str
    contact_block: str
    is_default: bool
    archived: bool
    created_at: str
    updated_at: str | None


@dataclass
class SerializedComplaint:
    id: str
    notification_id: str
    service_id: str
    service_name: str
    ses_feedback_id: str | None
    complaint_type: str | None
    complaint_date: str | None
    created_at: str


@dataclass
class SerializedServiceDataRetention:
    id: str
    service_id: str
    service_name: str
    notification_type: str
    days_of_retention: int
    created_at: str
    updated_at: str | None


@dataclass
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


@dataclass
class SerializedWebauthnCredential:
    id: str
    user_id: str
    name: str
    credential_data: str
    created_at: str
    updated_at: str | None
    logged_in_at: str | None


@dataclass
class SerializedLetterAttachment:
    id: str
    created_at: str
    created_by_id: str
    archived_at: str | None
    archived_by_id: str | None
    original_filename: str
    page_count: int


@dataclass
class SerializedUnsubscribeRequestReport:
    batch_id: str | None
    count: int
    created_at: str | None
    earliest_timestamp: str
    latest_timestamp: str
    processed_by_service_at: str | None
    is_a_batched_report: bool
    will_be_archived_at: str
    service_id: str


@dataclass
class SerializedServiceJoinRequest:
    id: str
    service_id: str
    created_at: str
    status: str
    status_changed_at: str | None
    reason: str | None
    contacted_service_users: list[str]
    status_changed_by: Any
    requester: Any


@dataclass
class SerializedReportRequest:
    id: str
    user_id: str
    service_id: str
    report_type: str
    status: str
    parameter: dict
    created_at: str
    updated_at: str
