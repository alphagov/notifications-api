

def create_post_sms_response_from_notification(
    notification_id, client_reference, template_id, template_version, service_id,
    content, from_number, url_root, scheduled_for
):
    resp = __create_notification_response(
        notification_id, client_reference, template_id, template_version, service_id, url_root, scheduled_for
    )
    resp['content'] = {
        'from_number': from_number,
        'body': content
    }
    return resp


def create_post_email_response_from_notification(
    notification_id,
    client_reference,
    template_id,
    template_version,
    service_id,
    content,
    subject,
    email_from,
    url_root,
    scheduled_for
):
    resp = __create_notification_response(
        notification_id, client_reference, template_id, template_version, service_id, url_root, scheduled_for
    )
    resp['content'] = {
        "from_email": email_from,
        "body": content,
        "subject": subject
    }
    return resp


def create_post_letter_response_from_notification(
    notification_id, client_reference, template_id, template_version, service_id,
    content, subject, url_root, scheduled_for
):
    resp = __create_notification_response(
        notification_id, client_reference, template_id, template_version, service_id, url_root, scheduled_for
    )
    resp['content'] = {
        "body": content,
        "subject": subject
    }
    return resp


def __create_notification_response(
    notification_id, client_reference, template_id, template_version, service_id, url_root, scheduled_for
):
    return {
        "id": notification_id,
        "reference": client_reference,
        "uri": "{}v2/notifications/{}".format(url_root, str(notification_id)),
        'template': {
            "id": template_id,
            "version": template_version,
            "uri": "{}services/{}/templates/{}".format(
                url_root,
                str(service_id),
                str(template_id)
            )
        },
        "scheduled_for": scheduled_for if scheduled_for else None
    }
