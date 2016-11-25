

class SendNotificationToQueueError(Exception):
    status_code = 500

    def __init__(self):
        self.message = "Failed to create the notification"
