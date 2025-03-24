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
