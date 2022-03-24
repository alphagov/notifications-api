from app.clients.sms import SmsClient, SmsClientResponseException


def get_reach_responses(status, detailed_status_code=None):
    if status == 'TODO-d':
        return ("delivered", "TODO: Delivered")
    elif status == 'TODO-tf':
        return ("temporary-failure", "TODO: Temporary failure")
    elif status == 'TODO-pf':
        return ("permanent-failure", "TODO: Permanent failure")
    else:
        raise KeyError


class ReachClientResponseException(SmsClientResponseException):
    pass  # TODO (custom exception for errors)


class ReachClient(SmsClient):

    def get_name(self):
        pass  # TODO

    def send_sms(self, to, content, reference, international, multi=True, sender=None):
        pass  # TODO
