import json
import logging
from contextvars import ContextVar

import requests
from flask import current_app
from notifications_utils.local_vars import LazyLocalGetter
from werkzeug.local import LocalProxy

from app import memo_resetters, notify_celery, signing
from app.config import QueueNames
from app.dao.inbound_sms_dao import dao_get_inbound_sms_by_id
from app.dao.returned_letters_dao import fetch_returned_letter_callback_data_dao
from app.dao.service_inbound_api_dao import get_service_inbound_api_for_service
from app.utils import DATETIME_FORMAT

# thread-local copies of persistent requests.Session
_requests_session_context_var: ContextVar[requests.Session] = ContextVar("service_callback_requests_session")
get_requests_session: LazyLocalGetter[requests.Session] = LazyLocalGetter(
    _requests_session_context_var,
    lambda: requests.Session(),
)
memo_resetters.append(lambda: get_requests_session.clear())
requests_session = LocalProxy(get_requests_session)


@notify_celery.task(bind=True, name="send-returned-letter", max_retries=5, default_retry_delay=300)
def send_returned_letter_to_service(self, encoded_returned_letter):
    returned_letter = signing.decode(encoded_returned_letter)

    data = {
        "notification_id": returned_letter["notification_id"],
        "reference": returned_letter["reference"],
        "date_sent": returned_letter["created_at"],
        "sent_by": returned_letter["email_address"],
        "template_name": returned_letter["template_name"],
        "template_id": returned_letter["template_id"],
        "template_version": returned_letter["template_version"],
        "spreadsheet_file_name": returned_letter["original_file_name"],
        "spreadsheet_row_number": returned_letter["job_row_number"],
        "upload_letter_file_name": returned_letter["upload_letter_file_name"],
    }

    _send_data_to_service_callback_api(
        self,
        data,
        returned_letter["service_callback_api_url"],
        returned_letter["service_callback_api_bearer_token"],
        "send_returned_letter_to_service",
    )


@notify_celery.task(
    bind=True, name="send-delivery-status", max_retries=5, default_retry_delay=300, early_log_level=logging.DEBUG
)
def send_delivery_status_to_service(self, notification_id, encoded_status_update):
    status_update = signing.decode(encoded_status_update)

    data = {
        "id": str(notification_id),
        "reference": status_update["notification_client_reference"],
        "to": status_update["notification_to"],
        "status": status_update["notification_status"],
        "created_at": status_update["notification_created_at"],
        "completed_at": status_update["notification_updated_at"],
        "sent_at": status_update["notification_sent_at"],
        "notification_type": status_update["notification_type"],
        "template_id": status_update["template_id"],
        "template_version": status_update["template_version"],
    }

    _send_data_to_service_callback_api(
        self,
        data,
        status_update["service_callback_api_url"],
        status_update["service_callback_api_bearer_token"],
        "send_delivery_status_to_service",
    )


@notify_celery.task(bind=True, name="send-complaint", max_retries=5, default_retry_delay=300)
def send_complaint_to_service(self, complaint_data):
    complaint = signing.decode(complaint_data)

    data = {
        "notification_id": complaint["notification_id"],
        "complaint_id": complaint["complaint_id"],
        "reference": complaint["reference"],
        "to": complaint["to"],
        "complaint_date": complaint["complaint_date"],
    }

    _send_data_to_service_callback_api(
        self,
        data,
        complaint["service_callback_api_url"],
        complaint["service_callback_api_bearer_token"],
        "send_complaint_to_service",
    )


@notify_celery.task(bind=True, name="send-inbound-sms", max_retries=5, default_retry_delay=300)
def send_inbound_sms_to_service(self, inbound_sms_id, service_id):
    inbound_api = get_service_inbound_api_for_service(service_id=service_id)
    if not inbound_api:
        # No API data has been set for this service
        return

    inbound_sms = dao_get_inbound_sms_by_id(service_id=service_id, inbound_id=inbound_sms_id)
    data = {
        "id": str(inbound_sms.id),
        # TODO: should we be validating and formatting the phone number here?
        "source_number": inbound_sms.user_number,
        "destination_number": inbound_sms.notify_number,
        "message": inbound_sms.content,
        "date_received": inbound_sms.provider_date.strftime(DATETIME_FORMAT),
    }

    _send_data_to_service_callback_api(
        self, data, inbound_api.url, inbound_api.bearer_token, "send_inbound_sms_to_service"
    )


def _send_data_to_service_callback_api(self, data, service_callback_url, token, function_name):
    object_id = data["notification_id"] if "notification_id" in data else data["id"]
    try:
        response = requests_session.request(
            method="POST",
            url=service_callback_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            timeout=5,
        )
        current_app.logger.info(
            "%s sending %s to %s, response %s",
            function_name,
            object_id,
            service_callback_url,
            response.status_code,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        current_app.logger.warning(
            "%s request failed for id: %s and url: %s. exception: %s",
            function_name,
            object_id,
            service_callback_url,
            e,
        )
        if not isinstance(e, requests.HTTPError) or e.response.status_code >= 500 or e.response.status_code == 429:
            try:
                self.retry(queue=QueueNames.CALLBACKS_RETRY)
            except self.MaxRetriesExceededError as e:
                current_app.logger.warning(
                    "Retry: %s has retried the max num of times for callback url %s and id: %s",
                    function_name,
                    service_callback_url,
                    object_id,
                )
        else:
            current_app.logger.warning(
                "%s callback is not being retried for id: %s and url: %s. exception: %s",
                function_name,
                object_id,
                service_callback_url,
                e,
            )


def create_delivery_status_callback_data(notification, service_callback_api):
    data = {
        "notification_id": str(notification.id),
        "notification_client_reference": notification.client_reference,
        "notification_to": notification.to,
        "notification_status": notification.status,
        "notification_created_at": notification.created_at.strftime(DATETIME_FORMAT),
        "notification_updated_at": (
            notification.updated_at.strftime(DATETIME_FORMAT) if notification.updated_at else None
        ),
        "notification_sent_at": notification.sent_at.strftime(DATETIME_FORMAT) if notification.sent_at else None,
        "notification_type": notification.notification_type,
        "service_callback_api_url": service_callback_api.url,
        "service_callback_api_bearer_token": service_callback_api.bearer_token,
        "template_id": str(notification.template_id),
        "template_version": notification.template_version,
    }
    return signing.encode(data)


def create_complaint_callback_data(complaint, notification, service_callback_api, recipient):
    data = {
        "complaint_id": str(complaint.id),
        "notification_id": str(notification.id),
        "reference": notification.client_reference,
        "to": recipient,
        "complaint_date": complaint.complaint_date.strftime(DATETIME_FORMAT),
        "service_callback_api_url": service_callback_api.url,
        "service_callback_api_bearer_token": service_callback_api.bearer_token,
    }
    return signing.encode(data)


def create_returned_letter_callback_data(notification_id, service_id, service_callback_api):
    returned_letter_data = fetch_returned_letter_callback_data_dao(notification_id, service_id)
    # The data mirrors that which is included in the returned letter report
    data = {
        "notification_id": str(returned_letter_data["notification_id"]),
        "reference": returned_letter_data["client_reference"] if returned_letter_data["api_key_id"] else None,
        "created_at": returned_letter_data["created_at"].strftime(DATETIME_FORMAT),
        "email_address": returned_letter_data["email_address"] or "API",
        # it doesn't make sense to show hidden/precompiled templates
        "template_name": returned_letter_data["template_name"] if not returned_letter_data["hidden"] else None,
        "template_id": str(returned_letter_data["template_id"] if not returned_letter_data["hidden"] else None),
        "template_version": returned_letter_data["template_version"] if not returned_letter_data["hidden"] else None,
        "original_file_name": returned_letter_data["original_file_name"],
        "job_row_number": returned_letter_data["job_row_number"],
        "upload_letter_file_name": returned_letter_data["client_reference"]
        if returned_letter_data["hidden"] and not returned_letter_data["api_key_id"]
        else None,
        "service_callback_api_url": service_callback_api.url,
        "service_callback_api_bearer_token": service_callback_api.bearer_token,
    }
    return signing.encode(data)
