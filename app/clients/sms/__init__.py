import platform
import socket
from abc import abstractmethod
from time import monotonic

import requests
from notifications_utils.clients.otel.utils import otel_duration_histogram
from urllib3.connection import HTTPConnection

from app.clients import Client, ClientException


class SmsClientResponseException(ClientException):
    """
    Base Exception for SmsClientsResponses
    """

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return f"SMS client error ({self.message})"


class SmsClient(Client):
    """
    Base Sms client for sending smss.
    """

    def __init__(self, current_app, statsd_client):
        super().__init__()
        self.current_app = current_app
        self.statsd_client = statsd_client

        self.requests_session = requests.Session()
        if platform.system() == "Linux":  # these are linux-specific socket options enabling tcp keepalive
            for adapter in self.requests_session.adapters.values():
                adapter.poolmanager.connection_pool_kw = {
                    "socket_options": HTTPConnection.default_socket_options
                    + [
                        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
                        (socket.SOL_TCP, socket.TCP_KEEPIDLE, 4),
                        (socket.SOL_TCP, socket.TCP_KEEPINTVL, 2),
                        (socket.SOL_TCP, socket.TCP_KEEPCNT, 8),
                    ],
                    **adapter.poolmanager.connection_pool_kw,
                }

    def record_outcome(self, success):
        if success:
            self.current_app.logger.info("Provider request for %s %s", self.name, "succeeded" if success else "failed")
            self.statsd_client.incr(f"clients.{self.name}.success")
        else:
            self.statsd_client.incr(f"clients.{self.name}.error")
            self.current_app.logger.warning(
                "Provider request for %s %s", self.name, "succeeded" if success else "failed"
            )

    @otel_duration_histogram("send_sms", attributes=lambda args, kwargs: {"provider_name": args[0].name})
    def send_sms(self, to, content, reference, international, sender):
        start_time = monotonic()

        try:
            response = self.try_send_sms(to, content, reference, international, sender)
            self.record_outcome(True)
        except SmsClientResponseException as e:
            self.record_outcome(False)
            raise e
        finally:
            elapsed_time = monotonic() - start_time
            self.statsd_client.timing(f"clients.{self.name}.request-time", elapsed_time)
            self.current_app.logger.info(
                "%s request for %s finished in %s",
                self.name,
                reference,
                elapsed_time,
                extra={
                    "provider_name": self.name,
                    "reference": reference,
                    "elapsed_time": elapsed_time,
                },
            )

        return response

    @abstractmethod
    def try_send_sms(self):
        pass
