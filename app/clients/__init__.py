
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


STATISTICS_REQUESTED = 'requested'
STATISTICS_DELIVERED = 'delivered'
STATISTICS_FAILURE = 'failure'
