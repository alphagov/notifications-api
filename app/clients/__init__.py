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


class Clients(object):
    sms_clients = {}
    email_clients = {}

    def init_app(self, sms_clients, email_clients):
        for client in sms_clients:
            self.sms_clients[client.name] = client

        for client in email_clients:
            self.email_clients[client.name] = client

    def sms_client(self, name):
        return self.sms_clients.get(name)

    def email_client(self, name):
        return self.email_clients.get(name)
