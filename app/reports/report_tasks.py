from app import notify_celery
from app.config import QueueNames


def send_service_task_to_report_queue(service):
    report_data = service.serialize_for_reports()
    notify_celery.send_task(
        name='update-reports-service-db',
        args=(report_data,),
        queue=QueueNames.REPORTS
    )


def send_template_task_to_report_queue(template):
    report_data = template.serialize_for_reports()
    notify_celery.send_task(
        name='update-reports-template-db',
        args=(report_data,),
        queue=QueueNames.REPORTS
    )


def send_notifications_task_to_report_queue(notification):
    report_data = notification.serialize_for_reports()
    notify_celery.send_task(
        name='update-reports-notification-db',
        args=(report_data,),
        queue=QueueNames.REPORTS
    )
