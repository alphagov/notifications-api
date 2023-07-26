from flask_openapi3 import OpenAPI


class NotifyApiFlaskApp(OpenAPI):
    @property
    def is_prod(self):
        return self.config["NOTIFY_ENVIRONMENT"] == "production"

    @property
    def is_test(self):
        return self.config["NOTIFY_ENVIRONMENT"] == "test"

    @property
    def should_send_zendesk_alerts(self):
        return self.is_test or self.is_prod
