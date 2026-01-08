from sqlalchemy import case, func, text
from sqlalchemy.orm import aliased

import app.dao.notifications_dao
from app import db as real_db
from app.dao.notifications_dao import db as db
from app.models import (
    Job,
    Notification,
    TemplateHistory,
    User,
)

EMAIL_STATUS_FORMATTED = {
    "created": "Sending",
    "sending": "Sending",
    "delivered": "Delivered",
    "pending": "Sending",
    "failed": "Failed",
    "technical-failure": "Tech issue",
    "temporary-failure": "Content or inbox issue",
    "permanent-failure": "No such address",
    "pending-virus-check": "Sending",
    "virus-scan-failed": "Attachment has virus",
    "validation-failed": "Content or inbox issue",
}

SMS_STATUS_FORMATTED = {
    "created": "Sending",
    "sending": "Sending",
    "pending": "Sending",
    "sent": "Sent",
    "delivered": "Delivered",
    "failed": "Failed",
    "technical-failure": "Tech issue",
    "temporary-failure": "Carrier issue",
    "permanent-failure": "No such number",
}


def build_notifications_copy_query(
    service_id,
    notification_type,
    notification_statuses=None,
    limit_days=7,
    chunk_size=None,
    older_than_id=None,
):
    db_for_scalar = app.dao.notifications_dao.db

    if notification_statuses is None:
        notification_statuses = []
    notifications = aliased(Notification, name="notifications")
    templates_history = aliased(TemplateHistory, name="templates_history")
    jobs = aliased(Job, name="jobs")
    users = aliased(User, name="users")

    query_filters = [
        notifications.service_id == service_id,
        notifications.notification_type == notification_type,
        notifications.created_at >= func.now() - text(f"interval '{limit_days} days'"),
        notifications.key_type != "test",
    ]

    if notification_statuses:
        statuses = Notification.substitute_status(notification_statuses)
        query_filters.append(notifications.status.in_(statuses))

    if older_than_id:
        older_than_notification = (
            db_for_scalar.session.query(Notification.created_at).filter(Notification.id == older_than_id).scalar()
        )
        if older_than_notification:
            query_filters.append(
                text(f"(notifications.created_at, notifications.id) < ('{older_than_notification}', '{older_than_id}')")
            )

    email_status_cases = [(notifications.status == k, v) for k, v in EMAIL_STATUS_FORMATTED.items()]
    sms_status_cases = [(notifications.status == k, v) for k, v in SMS_STATUS_FORMATTED.items()]

    if notification_type == "email":
        status_expr = case(*email_status_cases, else_=notifications.status)
    elif notification_type == "sms":
        status_expr = case(*sms_status_cases, else_=notifications.status)
    else:
        status_expr = notifications.status

    query_columns = [
        notifications.to.label("Recipient"),
        notifications.reference.label("Reference"),
        templates_history.name.label("Template"),
        notifications.notification_type.cast(real_db.String).label("Type"),
        func.coalesce(users.name, "").label("Sent by"),
        func.coalesce(users.email_address, "").label("Sent by email"),
        func.coalesce(jobs.original_file_name, "").label("Job"),
        status_expr.label("Status"),
        func.to_char(
            func.timezone("America/Toronto", func.timezone("UTC", notifications.created_at)), "YYYY-MM-DD HH24:MI:SS"
        ).label("Time"),
        notifications.api_key_id.label("API key name"),
        notifications.id,
        notifications.created_at,
    ]

    query = (
        real_db.session.query(*query_columns)
        .join(
            templates_history,
            (templates_history.id == notifications.template_id)
            & (templates_history.version == notifications.template_version),
        )
        .outerjoin(jobs, jobs.id == notifications.job_id)
        .outerjoin(users, users.id == notifications.created_by_id)
        .filter(*query_filters)
        .order_by(notifications.created_at.desc(), notifications.id.desc())
    )

    if chunk_size:
        query = query.limit(chunk_size)

    compiled = query.statement.compile(dialect=real_db.engine.dialect, compile_kwargs={"literal_binds": True})
    return str(compiled)


def execute_copy_to_bytes(query, include_header=True):
    from io import BytesIO

    from app.db_copy_utils import db as current_db

    buffer = BytesIO()
    copy_command = f"COPY ({query}) TO STDOUT WITH CSV"
    if include_header:
        copy_command += " HEADER"

    conn = current_db.engine.raw_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(query)
        rows = cursor.fetchall()
        row_count = len(rows)
        last_id = rows[-1][-2] if rows else None

        cursor.copy_expert(copy_command, buffer)
        buffer.seek(0)
        csv_bytes = buffer.getvalue()

        return csv_bytes, last_id, row_count
    finally:
        conn.close()


def get_notifications_csv_chunk(
    service_id,
    notification_type,
    notification_status_filter,
    limit_days,
    chunk_size,
    older_than_id=None,
    include_header=True,
):
    notification_statuses = [] if notification_status_filter == "all" else [notification_status_filter]
    query = build_notifications_copy_query(
        service_id=service_id,
        notification_type=notification_type,
        notification_statuses=notification_statuses,
        limit_days=limit_days,
        chunk_size=chunk_size,
        older_than_id=older_than_id,
    )
    return execute_copy_to_bytes(query, include_header=include_header)
