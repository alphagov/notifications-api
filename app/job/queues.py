import boto3
from flask import current_app

from app.config import QueueNames

sqs = boto3.client("sqs")


def get_message_group_id_for_queue(
    queue_name: QueueNames,
    service_id: str,
    notification_type: str | None = None,
    origin: str | None = None,  # "api" or "dashboard"
    key_type: str | None = None,  # normal, team, test
    emergency: bool | None = None,  # True/False
) -> str:
    if queue_name in (QueueNames.JOBS, QueueNames.DATABASE):
        # service + notif type
        return f"{service_id}#{notification_type}"

    if queue_name in (
        QueueNames.SEND_SMS,
        QueueNames.SEND_EMAIL,
        QueueNames.CREATE_LETTERS_PDF,
    ):
        # service + origin + key type because these are shared with API requests
        # emergency optional
        parts = [service_id]

        if origin:
            parts.append(origin)

        if key_type:
            parts.append(key_type)

        if emergency:
            parts.append("emergency")

        return "#".join(parts)

    # default to per service for now, this includes:
    # callbacks, antivirus, scheduled tasks, reporting, retry, etc.
    return str(service_id)


def fifo_message_kwargs(*, queue_name, service_id, **grouping_kwargs):
    if not current_app.config.get("ENABLE_SQS_FAIR_GROUPING"):
        current_app.logger.info(
            "SQS fair grouping disabled",
            extra={
                "queue": queue_name,
                "service_id": service_id,
            },
        )
        return {}

    is_fifo = is_fifo_queue(queue_name)
    group_id = get_message_group_id_for_queue(
        queue_name=queue_name,
        service_id=service_id,
        **grouping_kwargs,
    )

    current_app.logger.info(
        "Is queue FIFO",
        extra={
            "queue": queue_name,
            "service_id": service_id,
            "is_fifo_queue": is_fifo,
            "group_id": group_id,
        },
    )

    return {"message_properties": {"MessageGroupId": group_id}}


def get_queue_url(queue_name: str) -> str:
    prefix = current_app.config["NOTIFICATION_QUEUE_PREFIX"]
    region = current_app.config["AWS_REGION"]
    account_id = current_app.config["AWS_ACCOUNT_ID"]

    return f"https://sqs.{region}.amazonaws.com/{account_id}/{prefix}{queue_name}"


def is_fifo_queue(queue_name: str) -> bool:
    response = sqs.get_queue_attributes(
        QueueUrl=get_queue_url(queue_name),
        AttributeNames=["All"],
    )

    current_app.logger.info(
        "SQS fair grouping attributes all",
        extra={
            "queue": queue_name,
            "attributes": response["Attributes"],
        },
    )

    return response["Attributes"].get("FifoQueue") == "true"
