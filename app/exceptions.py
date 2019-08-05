from flask import current_app


class DVLAException(Exception):
    def __init__(self, message):
        self.message = message


class NotificationTechnicalFailureException(Exception):
    def __init__(self, message):
        self.message = message
        current_app.logger.exception(message)


class ArchiveValidationError(Exception):
    pass
