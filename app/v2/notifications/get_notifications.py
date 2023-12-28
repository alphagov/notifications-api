import uuid
from io import BytesIO
from typing import Annotated

from flask import current_app, jsonify, request, send_file, url_for
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_serializer
from pydantic_core.core_schema import SerializerFunctionWrapHandler

from app import api_user, authenticated_service
from app.constants import (
    LETTER_TYPE,
    LITERAL_TEMPLATE_TYPES,
    NOTIFICATION_PENDING_VIRUS_CHECK,
    NOTIFICATION_TECHNICAL_FAILURE,
    NOTIFICATION_VIRUS_SCAN_FAILED,
    NotificationStatus,
)
from app.dao import notifications_dao
from app.letters.utils import get_letter_pdf_and_metadata
from app.models import NotificationSerializer
from app.openapi import CustomErrorBaseModel, omit_if_none
from app.v2.errors import BadRequestError, PDFNotReadyError
from app.v2.notifications import v2_notification_blueprint


class GetNotificationByIdPath(CustomErrorBaseModel):
    notification_id: uuid.UUID

    override_errors = {("uuid_parsing", ("notification_id",)): "notification_id is not a valid UUID"}


@v2_notification_blueprint.get("/<notification_id>", responses={"200": NotificationSerializer})
def get_notification_by_id(path: GetNotificationByIdPath):
    notification = notifications_dao.get_notification_with_personalisation(
        authenticated_service.id, path.notification_id, key_type=None
    )
    return (
        NotificationSerializer.model_validate(notification).model_dump_json(),
        200,
        {"content-type": "application/json"},
    )


@v2_notification_blueprint.get(
    "/<notification_id>/pdf",
    responses={
        "200": {
            "description": "The raw PDF for a letter notification",
            "content": {
                "application/pdf": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        }
    },
)
def get_pdf_for_notification(path: GetNotificationByIdPath):
    notification = notifications_dao.get_notification_by_id(path.notification_id, authenticated_service.id, _raise=True)

    if notification.notification_type != LETTER_TYPE:
        raise BadRequestError(message="Notification is not a letter")

    if notification.status == NOTIFICATION_VIRUS_SCAN_FAILED:
        raise BadRequestError(message="File did not pass the virus scan")

    if notification.status == NOTIFICATION_TECHNICAL_FAILURE:
        raise BadRequestError(message="PDF not available for letters in status {}".format(notification.status))

    if notification.status == NOTIFICATION_PENDING_VIRUS_CHECK:
        raise PDFNotReadyError()

    try:
        pdf_data, metadata = get_letter_pdf_and_metadata(notification)
    except Exception as e:
        raise PDFNotReadyError() from e

    return send_file(path_or_file=BytesIO(pdf_data), mimetype="application/pdf")


class PaginationLinks(BaseModel):
    next: Annotated[str, omit_if_none] = Field(None)
    current: str

    @model_serializer(mode="wrap")
    def _serialize(self, handler: SerializerFunctionWrapHandler):
        omit_fields = {k for k, v in self.model_fields.items() for m in v.metadata if m is omit_if_none}

        return {k: v for k, v in handler(self).items() if k not in omit_fields or v is not None}


class ListNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notifications: list[NotificationSerializer]
    links: PaginationLinks


class ListNotificationQuery(CustomErrorBaseModel):
    template_type: LITERAL_TEMPLATE_TYPES = Field(None)
    status: list[NotificationStatus] = Field(None)
    reference: str = Field(None)
    older_than: uuid.UUID = Field(None)
    include_jobs: str = Field(None)  # stringly typed so any non-empty is truthy

    override_errors = {
        ("enum", ("status", 0)): (
            "status {input} is not one of [cancelled, created, sending, "
            "sent, delivered, pending, failed, technical-failure, temporary-failure, permanent-failure, "
            "pending-virus-check, validation-failed, virus-scan-failed, returned-letter, accepted, received]"
        ),
        ("literal_error", ("template_type",)): "template_type {input} is not one of [sms, email, letter]",
        ("uuid_parsing", ("older_than",)): "older_than is not a valid UUID",
    }

    @field_serializer("status")
    def stringify_statuses(self, val):
        if val:
            return [v.value for v in val]
        return None


@v2_notification_blueprint.get("", responses={"200": ListNotificationResponse})
def get_notifications(query: ListNotificationQuery):
    paginated_notifications = notifications_dao.get_notifications_for_service(
        str(authenticated_service.id),
        filter_dict=request.args,  # fixme: shouldn't need this with proper query args parsing
        key_type=api_user.key_type,
        personalisation=True,
        older_than=query.older_than,
        client_reference=query.reference,
        page_size=current_app.config.get("API_PAGE_SIZE"),
        include_jobs=query.include_jobs,
        count_pages=False,
    )

    def _build_links(notifications):
        _links = {
            "current": url_for(".get_notifications", _external=True, **query.model_dump()),
        }

        if len(notifications):
            next_query_params = dict(request.args, older_than=notifications[-1].id)
            _links["next"] = url_for(".get_notifications", _external=True, **next_query_params)

        return _links

    return (
        jsonify(
            ListNotificationResponse(
                notifications=paginated_notifications.items, links=_build_links(paginated_notifications.items)
            ).model_dump()
        ),
        200,
    )
