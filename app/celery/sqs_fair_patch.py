import logging

from kombu.transport.SQS import Channel as SQSChannel

_original_put = SQSChannel._put


def _put_with_message_group(self, queue, message, **kwargs):
    headers = (message.get("properties") or {}).get("headers") or {}
    message_group_id = headers.get("MessageGroupId")

    if message_group_id:
        logging.info(f"🟢 Fair queue message -> Queue={queue}, MessageGroupId={message_group_id}")
        kwargs = {**kwargs, "MessageGroupId": str(message_group_id)}

    return _original_put(self, queue, message, **kwargs)


SQSChannel._put = _put_with_message_group
