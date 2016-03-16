from utils.recipients import format_phone_number, validate_phone_number


def allowed_send_to_number(service, to):
    if service.restricted and format_phone_number(validate_phone_number(to)) not in [
        format_phone_number(validate_phone_number(user.mobile_number)) for user in service.users
    ]:
        return False
    return True


def allowed_send_to_email(service, to):
    if service.restricted and to not in [user.email_address for user in service.users]:
        return False
    return True
