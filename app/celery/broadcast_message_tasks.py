import requests
from flask import current_app
from notifications_utils.statsd_decorators import statsd

from app import notify_celery

from app.dao.broadcast_message_dao import dao_get_broadcast_message_by_id


@notify_celery.task(name="send-broadcast-message")
@statsd(namespace="tasks")
def send_broadcast_message(broadcast_message_id, provider='stub-1'):
    # imports of schemas from tasks have to happen within functions to prevent
    # `AttributeError: 'DummySession' object has no attribute 'query'` errors in unrelated tests
    from app.schemas import template_schema

    broadcast_message = dao_get_broadcast_message_by_id(broadcast_message_id)

    current_app.logger.info(
        f'sending broadcast_message {broadcast_message_id} '
        f'status {broadcast_message.status} to {provider}'
    )

    payload = {
        "template": template_schema.dump(broadcast_message.template).data,
        "broadcast_message": broadcast_message.serialize(),
    }
    resp = requests.post(
        f'{current_app.config["CBC_PROXY_URL"]}/broadcasts/{provider}',
        json=payload
    )
    resp.raise_for_status()

    current_app.logger.info(
        f'broadcast_message {broadcast_message.id} '
        f'status {broadcast_message.status} sent to {provider}'
    )
