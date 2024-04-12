from time import monotonic

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

    def init_app(self, current_app, statsd_client):
        self.current_app = current_app
        self.statsd_client = statsd_client

    def record_outcome(self, success):
        if success:
            self.current_app.logger.info("Provider request for %s %s", self.name, "succeeded" if success else "failed")
            self.statsd_client.incr(f"clients.{self.name}.success")
        else:
            self.statsd_client.incr(f"clients.{self.name}.error")
            self.current_app.logger.warning(
                "Provider request for %s %s", self.name, "succeeded" if success else "failed"
            )

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

    def try_send_sms(self, *args, **kwargs):
        raise NotImplementedError("TODO Need to implement.")

    @property
    def name(self):
        raise NotImplementedError("TODO Need to implement.")
