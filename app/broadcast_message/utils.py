from datetime import datetime

from flask import current_app

from app.celery.broadcast_message_tasks import send_broadcast_event
from app.config import QueueNames
from app.dao.dao_utils import dao_save_object
from app.errors import InvalidRequest
from app.models import (
    BroadcastEvent,
    BroadcastEventMessageType,
    BroadcastStatusType,
)


def validate_and_update_broadcast_message_status(broadcast_message, new_status, updating_user=None, api_key_id=None):
    _validate_broadcast_update(broadcast_message, new_status, updating_user)

    if new_status == BroadcastStatusType.BROADCASTING:
        broadcast_message.approved_at = datetime.utcnow()
        broadcast_message.approved_by = updating_user

    if new_status == BroadcastStatusType.CANCELLED:
        broadcast_message.cancelled_at = datetime.utcnow()
        broadcast_message.cancelled_by = updating_user
        broadcast_message.cancelled_by_api_key_id = api_key_id

    current_app.logger.info(
        f'broadcast_message {broadcast_message.id} moving from {broadcast_message.status} to {new_status}'
    )
    broadcast_message.status = new_status

    dao_save_object(broadcast_message)

    if new_status in {BroadcastStatusType.BROADCASTING, BroadcastStatusType.CANCELLED}:
        _create_broadcast_event(broadcast_message)


def _validate_broadcast_update(broadcast_message, new_status, updating_user):
    if new_status not in BroadcastStatusType.ALLOWED_STATUS_TRANSITIONS[broadcast_message.status]:
        raise InvalidRequest(
            f'Cannot move broadcast_message {broadcast_message.id} from {broadcast_message.status} to {new_status}',
            status_code=400
        )

    if new_status == BroadcastStatusType.BROADCASTING:
        # training mode services can approve their own broadcasts
        if updating_user == broadcast_message.created_by and not broadcast_message.service.restricted:
            raise InvalidRequest(
                f'User {updating_user.id} cannot approve their own broadcast_message {broadcast_message.id}',
                status_code=400
            )
        elif len(broadcast_message.areas['simple_polygons']) == 0:
            raise InvalidRequest(
                f'broadcast_message {broadcast_message.id} has no selected areas and so cannot be broadcasted.',
                status_code=400
            )


def _create_broadcast_event(broadcast_message):
    """
    If the service is live and the broadcast message is not stubbed, creates a broadcast event, stores it in the
    database, and triggers the task to send the CAP XML off.
    """
    service = broadcast_message.service

    if not broadcast_message.stubbed and not service.restricted:
        msg_types = {
            BroadcastStatusType.BROADCASTING: BroadcastEventMessageType.ALERT,
            BroadcastStatusType.CANCELLED: BroadcastEventMessageType.CANCEL,
        }

        event = BroadcastEvent(
            service=service,
            broadcast_message=broadcast_message,
            message_type=msg_types[broadcast_message.status],
            transmitted_content={"body": broadcast_message.content},
            transmitted_areas=broadcast_message.areas,
            # TODO: Probably move this somewhere more standalone too and imply that it shouldn't change. Should it
            # include a service based identifier too? eg "flood-warnings@notifications.service.gov.uk" or similar
            transmitted_sender='notifications.service.gov.uk',

            # TODO: Should this be set to now? Or the original starts_at?
            transmitted_starts_at=broadcast_message.starts_at,
            transmitted_finishes_at=broadcast_message.finishes_at,
        )

        dao_save_object(event)

        send_broadcast_event.apply_async(
            kwargs={'broadcast_event_id': str(event.id)},
            queue=QueueNames.BROADCASTS
        )
    elif broadcast_message.stubbed != service.restricted:
        # It's possible for a service to create a broadcast in trial mode, and then approve it after the
        # service is live (or vice versa). We don't think it's safe to send such broadcasts, as the service
        # has changed since they were created. Log an error instead.
        current_app.logger.error(
            f'Broadcast event not created. Stubbed status of broadcast message was {broadcast_message.stubbed}'
            f' but service was {"in trial mode" if service.restricted else "live"}'
        )
