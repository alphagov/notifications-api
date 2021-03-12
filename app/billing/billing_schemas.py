from datetime import datetime

create_or_update_free_sms_fragment_limit_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST annual billing schema",
    "type": "object",
    "title": "Create",
    "properties": {
        "free_sms_fragment_limit": {"type": "integer", "minimum": 1},
    },
    "required": ["free_sms_fragment_limit"]
}


def serialize_ft_billing_remove_emails(data):
    results = []
    billed_notifications = [x for x in data if x.notification_type != 'email']
    for notification in billed_notifications:
        json_result = {
            "month": (datetime.strftime(notification.month, "%B")),
            "notification_type": notification.notification_type,
            "billing_units": notification.billable_units,
            "rate": float(notification.rate),
            "postage": notification.postage,
        }
        results.append(json_result)
    return results


def serialize_ft_billing_yearly_totals(data):
    yearly_totals = []
    for total in data:
        json_result = {
            "notification_type": total.notification_type,
            "billing_units": total.billable_units,
            "rate": float(total.rate),
            "letter_total": float(total.billable_units * total.rate) if total.notification_type == 'letter' else 0
        }
        yearly_totals.append(json_result)

    return yearly_totals
