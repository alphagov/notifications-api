from datetime import (
    datetime,
    timedelta
)

from flask import current_app
from notifications_utils.statsd_decorators import statsd
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError

from app import notify_celery, zendesk_client
from app.celery.tasks import (
    process_job,
    get_recipient_csv_and_template_and_sender_id,
    process_row
)
from app.celery.letters_pdf_tasks import create_letters_pdf
from app.config import QueueNames, TaskNames
from app.dao.invited_org_user_dao import delete_org_invitations_created_more_than_two_days_ago
from app.dao.invited_user_dao import delete_invitations_created_more_than_two_days_ago
from app.dao.jobs_dao import (
    dao_set_scheduled_jobs_to_pending,
    find_jobs_with_missing_rows,
    find_missing_row_for_job
)
from app.dao.jobs_dao import dao_update_job
from app.dao.notifications_dao import (
    dao_get_scheduled_notifications,
    set_scheduled_notification_to_processed,
    notifications_not_yet_sent,
    dao_precompiled_letters_still_pending_virus_check,
    dao_old_letters_with_created_status,
    letters_missing_from_sending_bucket,
    is_delivery_slow_for_providers,
)
from app.dao.provider_details_dao import dao_reduce_sms_provider_priority
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.dao.services_dao import dao_find_services_sending_to_tv_numbers
from app.models import (
    Job,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_ERROR,
    SMS_TYPE,
    EMAIL_TYPE,
)
from app.notifications.process_notifications import send_notification_to_queue
from app.v2.errors import JobIncompleteError

from app.service.utils import get_services_with_high_failure_rates


@notify_celery.task(name="run-scheduled-jobs")
@statsd(namespace="tasks")
def run_scheduled_jobs():
    try:
        for job in dao_set_scheduled_jobs_to_pending():
            process_job.apply_async([str(job.id)], queue=QueueNames.JOBS)
            current_app.logger.info("Job ID {} added to process job queue".format(job.id))
    except SQLAlchemyError:
        current_app.logger.exception("Failed to run scheduled jobs")
        raise


@notify_celery.task(name='send-scheduled-notifications')
@statsd(namespace="tasks")
def send_scheduled_notifications():
    try:
        scheduled_notifications = dao_get_scheduled_notifications()
        for notification in scheduled_notifications:
            send_notification_to_queue(notification, notification.service.research_mode)
            set_scheduled_notification_to_processed(notification.id)
        current_app.logger.info(
            "Sent {} scheduled notifications to the provider queue".format(len(scheduled_notifications)))
    except SQLAlchemyError:
        current_app.logger.exception("Failed to send scheduled notifications")
        raise


@notify_celery.task(name="delete-verify-codes")
@statsd(namespace="tasks")
def delete_verify_codes():
    try:
        start = datetime.utcnow()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} verify codes".format(start, datetime.utcnow(), deleted)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete verify codes")
        raise


@notify_celery.task(name="delete-invitations")
@statsd(namespace="tasks")
def delete_invitations():
    try:
        start = datetime.utcnow()
        deleted_invites = delete_invitations_created_more_than_two_days_ago()
        deleted_invites += delete_org_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started {} finished {} deleted {} invitations".format(start, datetime.utcnow(), deleted_invites)
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name='switch-current-sms-provider-on-slow-delivery')
@statsd(namespace="tasks")
def switch_current_sms_provider_on_slow_delivery():
    """
    Reduce provider's priority if at least 30% of notifications took more than four minutes to be delivered
    in the last ten minutes. If both providers are slow, don't do anything. If we changed the providers in the
    last ten minutes, then don't update them again either.
    """
    slow_delivery_notifications = is_delivery_slow_for_providers(
        threshold=0.3,
        created_at=datetime.utcnow() - timedelta(minutes=10),
        delivery_time=timedelta(minutes=4),
    )

    # only adjust if some values are true and some are false - ie, don't adjust if all providers are fast or
    # all providers are slow
    if len(set(slow_delivery_notifications.values())) != 1:
        for provider_name, is_slow in slow_delivery_notifications.items():
            if is_slow:
                current_app.logger.warning('Slow delivery notifications detected for provider {}'.format(provider_name))
                dao_reduce_sms_provider_priority(provider_name, time_threshold=timedelta(minutes=10))


@notify_celery.task(name='check-job-status')
@statsd(namespace="tasks")
def check_job_status():
    """
    every x minutes do this check
    select
    from jobs
    where job_status == 'in progress'
    and template_type in ('sms', 'email')
    and scheduled_at or created_at is older that 30 minutes.
    if any results then
        raise error
        process the rows in the csv that are missing (in another task) just do the check here.
    """
    thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
    thirty_five_minutes_ago = datetime.utcnow() - timedelta(minutes=35)

    jobs_not_complete_after_30_minutes = Job.query.filter(
        Job.job_status == JOB_STATUS_IN_PROGRESS,
        and_(thirty_five_minutes_ago < Job.processing_started, Job.processing_started < thirty_minutes_ago)
    ).order_by(Job.processing_started).all()

    # temporarily mark them as ERROR so that they don't get picked up by future check_job_status tasks
    # if they haven't been re-processed in time.
    job_ids = []
    for job in jobs_not_complete_after_30_minutes:
        job.job_status = JOB_STATUS_ERROR
        dao_update_job(job)
        job_ids.append(str(job.id))

    if job_ids:
        notify_celery.send_task(
            name=TaskNames.PROCESS_INCOMPLETE_JOBS,
            args=(job_ids,),
            queue=QueueNames.JOBS
        )
        raise JobIncompleteError("Job(s) {} have not completed.".format(job_ids))


@notify_celery.task(name='replay-created-notifications')
@statsd(namespace="tasks")
def replay_created_notifications():
    # if the notification has not be send after 1 hour, then try to resend.
    resend_created_notifications_older_than = (60 * 60)
    for notification_type in (EMAIL_TYPE, SMS_TYPE):
        notifications_to_resend = notifications_not_yet_sent(
            resend_created_notifications_older_than,
            notification_type
        )

        if len(notifications_to_resend) > 0:
            current_app.logger.info("Sending {} {} notifications "
                                    "to the delivery queue because the notification "
                                    "status was created.".format(len(notifications_to_resend), notification_type))

        for n in notifications_to_resend:
            send_notification_to_queue(notification=n, research_mode=n.service.research_mode)

    # if the letter has not be send after an hour, then create a zendesk ticket
    letters = letters_missing_from_sending_bucket(resend_created_notifications_older_than)

    if len(letters) > 0:
        msg = "{} letters were created over an hour ago, " \
              "but do not have an updated_at timestamp or billable units. " \
              "\n Creating app.celery.letters_pdf_tasks.create_letters tasks to upload letter to S3 " \
              "and update notifications for the following notification ids: " \
              "\n {}".format(len(letters), [x.id for x in letters])

        current_app.logger.info(msg)
        for letter in letters:
            create_letters_pdf.apply_async([letter.id], queue=QueueNames.LETTERS)


@notify_celery.task(name='check-precompiled-letter-state')
@statsd(namespace="tasks")
def check_precompiled_letter_state():
    letters = dao_precompiled_letters_still_pending_virus_check()

    if len(letters) > 0:
        letter_ids = [str(letter.id) for letter in letters]

        msg = "{} precompiled letters have been pending-virus-check for over 90 minutes. " \
              "Notifications: {}".format(len(letters), letter_ids)

        current_app.logger.exception(msg)

        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            zendesk_client.create_ticket(
                subject="[{}] Letters still pending virus check".format(current_app.config['NOTIFY_ENVIRONMENT']),
                message=msg,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )


@notify_celery.task(name='check-templated-letter-state')
@statsd(namespace="tasks")
def check_templated_letter_state():
    letters = dao_old_letters_with_created_status()

    if len(letters) > 0:
        letter_ids = [str(letter.id) for letter in letters]

        msg = "{} letters were created before 17.30 yesterday and still have 'created' status. " \
              "Notifications: {}".format(len(letters), letter_ids)

        current_app.logger.exception(msg)

        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            zendesk_client.create_ticket(
                subject="[{}] Letters still in 'created' status".format(current_app.config['NOTIFY_ENVIRONMENT']),
                message=msg,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )


@notify_celery.task(name='check-for-missing-rows-in-completed-jobs')
def check_for_missing_rows_in_completed_jobs():
    jobs_and_job_size = find_jobs_with_missing_rows()
    for x in jobs_and_job_size:
        job = x[1]
        missing_rows = find_missing_row_for_job(job.id, job.notification_count)
        for row_to_process in missing_rows:
            recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)
            for row in recipient_csv.get_rows():
                if row.index == row_to_process.missing_row:
                    current_app.logger.info(
                        "Processing missing row: {} for job: {}".format(row_to_process.missing_row, job.id))
                    process_row(row, template, job, job.service, sender_id=sender_id)


@notify_celery.task(name='check-for-services-with-high-failure-rates-or-sending-to-tv-numbers')
@statsd(namespace="tasks")
def check_for_services_with_high_failure_rates_or_sending_to_tv_numbers():
    start_date = (datetime.utcnow() - timedelta(days=1))
    end_date = datetime.utcnow()
    message = ""

    services_with_failures = get_services_with_high_failure_rates(start_date=start_date, end_date=end_date)
    services_sending_to_tv_numbers = dao_find_services_sending_to_tv_numbers(
        threshold=100,
        start_date=start_date,
        end_date=end_date
    )

    if services_with_failures:
        message += "{} service(s) have had high permanent-failure rates for sms messages in last 24 hours:\n".format(
            len(services_with_failures)
        )
        for service in services_with_failures:
            message += "service id: {} failure rate: {},\n".format(service["id"], service["permanent_failure_rate"])
    elif services_sending_to_tv_numbers:
        message += "{} service(s) have sent over 100 sms messages to tv numbers in last 24 hours:\n".format(
            len(services_sending_to_tv_numbers)
        )
        for service in services_sending_to_tv_numbers:
            message += "service id: {}, count of sms to tv numbers: {},\n".format(
                service.service_id, service.notification_count
            )

    if services_with_failures or services_sending_to_tv_numbers:
        current_app.logger.exception(message)

        if current_app.config['NOTIFY_ENVIRONMENT'] in ['live', 'production', 'test']:
            zendesk_client.create_ticket(
                subject="[{}] High failure rates for sms spotted for services".format(
                    current_app.config['NOTIFY_ENVIRONMENT']
                ),
                message=message,
                ticket_type=zendesk_client.TYPE_INCIDENT
            )
