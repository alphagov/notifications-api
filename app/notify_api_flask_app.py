from flask import Flask


class NotifyApiFlaskApp(Flask):
    @property
    def should_send_zendesk_alerts(self):
        return self.config["SEND_ZENDESK_ALERTS_ENABLED"]

    @property
    def should_check_slow_text_message_delivery(self):
        return self.config["CHECK_SLOW_TEXT_MESSAGE_DELIVERY"]

    @property
    def should_send_weekly_user_research_email(self):
        return self.config["WEEKLY_USER_RESEARCH_EMAIL_ENABLED"]
