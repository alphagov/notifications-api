from abc import ABC, abstractmethod


class ClientException(Exception):
    """
    Base Exceptions for sending notifications that fail
    """


class Client(ABC):
    """
    Base client for sending notifications.
    """

    @property
    @abstractmethod
    def name(self):
        pass


STATISTICS_REQUESTED = "requested"
STATISTICS_DELIVERED = "delivered"
STATISTICS_FAILURE = "failure"


class NotificationProviderClients:
    def __init__(self, sms_clients, email_clients):
        self.sms_clients = {**sms_clients}
        self.email_clients = {**email_clients}

    def get_sms_client(self, name):
        return self.sms_clients.get(name)

    def get_email_client(self, name):
        return self.email_clients.get(name)

    def get_client_by_name_and_type(self, name, notification_type):
        assert notification_type in ["email", "sms"]

        if notification_type == "email":
            return self.get_email_client(name)

        if notification_type == "sms":
            return self.get_sms_client(name)
