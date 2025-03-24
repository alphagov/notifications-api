from app.dao.notifications_dao import get_notifications_for_service


def convert_notifications_to_csv(serialized_notifications):
    values = []
    for notification in serialized_notifications:
        values.append(
            (
                # the recipient for precompiled letters is the full address block
                notification["recipient"].splitlines()[0].lstrip().rstrip(" ,"),
                notification["client_reference"],
                notification["template_name"],
                notification["template_type"],
                notification["created_by_name"] or "",
                notification["created_by_email_address"] or "",
                notification["job_name"] or "",
                notification["status"],
                notification["created_at"],
                notification["api_key_name"] or "",
            )
        )
    return values


def get_notifications_by_batch(service_id, status, template_type, page, page_size, limit_days):
    statuses = [status] if status != "all" else ["sending", "delivered", "created"]

    notifications = get_notifications_for_service(
        service_id=service_id,
        filter_dict={
            "template_type": template_type,
            "status": statuses,
        },
        page=page,
        page_size=page_size,
        limit_days=limit_days,
    )

    serialized_notifications = [notification.serialize_for_csv() for notification in notifications]
    return serialized_notifications
