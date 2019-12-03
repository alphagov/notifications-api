import itertools

from notifications_utils.recipients import allowed_to_send_to

from app.dao.services_dao import dao_find_real_sms_notification_count_by_status_for_live_services

from app.models import (
    ServiceWhitelist,
    MOBILE_TYPE, EMAIL_TYPE,
    KEY_TYPE_TEST, KEY_TYPE_TEAM, KEY_TYPE_NORMAL)

from app.service import statistics


def get_recipients_from_request(request_json, key, type):
    return [(type, recipient) for recipient in request_json.get(key)]


def get_whitelist_objects(service_id, request_json):
    return [
        ServiceWhitelist.from_string(service_id, type, recipient)
        for type, recipient in (
            get_recipients_from_request(request_json,
                                        'phone_numbers',
                                        MOBILE_TYPE) +
            get_recipients_from_request(request_json,
                                        'email_addresses',
                                        EMAIL_TYPE)
        )
    ]


def service_allowed_to_send_to(recipient, service, key_type, allow_whitelisted_recipients=True):
    if key_type == KEY_TYPE_TEST:
        return True

    if key_type == KEY_TYPE_NORMAL and not service.restricted:
        return True

    team_members = itertools.chain.from_iterable(
        [user.mobile_number, user.email_address] for user in service.users
    )
    whitelist_members = [
        member.recipient for member in service.whitelist
        if allow_whitelisted_recipients
    ]

    if (
        (key_type == KEY_TYPE_NORMAL and service.restricted) or
        (key_type == KEY_TYPE_TEAM)
    ):
        return allowed_to_send_to(
            recipient,
            itertools.chain(
                team_members,
                whitelist_members
            )
        )


def get_services_with_high_failure_rates(start_date, end_date, rate=0.25, threshold=100):
    stats = dao_find_real_sms_notification_count_by_status_for_live_services(
        start_date=start_date,
        end_date=end_date,
    )
    results = []
    for service_id, rows in itertools.groupby(stats, lambda x: x.service_id):
        rows = list(rows)

        permanent_failure_rate = statistics.get_rate_of_permanent_failures_for_service(rows, threshold=threshold)
        if permanent_failure_rate >= rate:
            results.append({
                'id': str(rows[0].service_id),
                'permanent_failure_rate': permanent_failure_rate
            })
    return results
