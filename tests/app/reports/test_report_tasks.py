from app.reports.report_tasks import (
    send_service_task_to_report_queue,
    send_template_task_to_report_queue,
    send_notifications_task_to_report_queue)


def test_send_service_task_to_report_queue(sample_user, sample_service, mocker,):
    mock_celery = mocker.patch("app.letters.rest.notify_celery.send_task")

    json = sample_service.serialize_for_reports()

    send_service_task_to_report_queue(sample_service)
    mock_celery.assert_called_with(name='update-reports-service-db', args=(json,), queue='reports-tasks')


def test_send_template_task_to_report_queue(sample_template, mocker,):
    mock_celery = mocker.patch("app.letters.rest.notify_celery.send_task")

    json = sample_template.serialize_for_reports()

    send_template_task_to_report_queue(sample_template)
    mock_celery.assert_called_with(name='update-reports-template-db', args=(json,), queue='reports-tasks')


def test_send_notification_task_to_report_queue(sample_notification, mocker,):
    mock_celery = mocker.patch("app.letters.rest.notify_celery.send_task")

    json = sample_notification.serialize_for_reports()

    send_notifications_task_to_report_queue(sample_notification)
    mock_celery.assert_called_with(name='update-reports-notification-db', args=(json,), queue='reports-tasks')
