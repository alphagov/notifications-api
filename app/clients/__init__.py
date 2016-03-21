
class ClientException(Exception):
    '''
    Base Exceptions for sending notifications that fail
    '''
    pass


class Client(object):
    '''
    Base client for sending notifications.
    '''
    pass


class ClientResponse:
    def __init__(self):
        self.__response_model__ = None

    def response_code_to_object(self, response_code):
        return self.__response_model__[response_code]

    def response_code_to_message(self, response_code):
        return self.response_code_to_object(response_code)['message']

    def response_code_to_notification_status(self, response_code):
        print(response_code)
        return self.response_code_to_object(response_code)['notification_status']

    def response_code_to_notification_statistics_status(self, response_code):
        return self.response_code_to_object(response_code)['notification_statistics_status']

    def response_code_to_notification_success(self, response_code):
        return self.response_code_to_object(response_code)['success']
