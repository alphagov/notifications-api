import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta

import jinja2
import sentry_sdk
from flask import current_app
from notifications_utils.clients.zendesk.zendesk_client import (
    NotifySupportTicket,
    NotifySupportTicketAttachment,
    NotifySupportTicketComment,
    NotifySupportTicketStatus,
    NotifyTicketType,
)
from notifications_utils.timezones import convert_utc_to_bst
from redis.exceptions import LockError
from sqlalchemy import and_, between
from sqlalchemy.exc import SQLAlchemyError

from app import db, dvla_client, notify_celery, redis_store, statsd_client, zendesk_client
from app.aws import s3
from app.celery.letters_pdf_tasks import get_pdf_for_templated_letter
from app.celery.tasks import (
    get_recipient_csv_and_template_and_sender_id,
    process_incomplete_jobs,
    process_job,
    process_row,
)
from app.clients.letter.dvla import DvlaRetryableException
from app.config import QueueNames, TaskNames
from app.constants import (
    EMAIL_TYPE,
    JOB_STATUS_ERROR,
    JOB_STATUS_IN_PROGRESS,
    JOB_STATUS_PENDING,
    SMS_TYPE,
    CacheKeys,
)
from app.cronitor import cronitor
from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.date_util import get_current_financial_year_start_year
from app.dao.inbound_numbers_dao import dao_get_available_inbound_numbers
from app.dao.invited_org_user_dao import (
    delete_org_invitations_created_more_than_two_days_ago,
)
from app.dao.invited_user_dao import (
    delete_invitations_created_more_than_two_days_ago,
)
from app.dao.jobs_dao import (
    dao_set_scheduled_jobs_to_pending,
    dao_update_job,
    find_jobs_with_missing_rows,
    find_missing_row_for_job,
)
from app.dao.notifications_dao import (
    SlowProviderDeliveryReport,
    dao_old_letters_with_created_status,
    dao_precompiled_letters_still_pending_virus_check,
    get_slow_text_message_delivery_reports_by_provider,
    is_delivery_slow_for_providers,
    letters_missing_from_sending_bucket,
    notifications_not_yet_sent,
)
from app.dao.provider_details_dao import (
    dao_adjust_provider_priority_back_to_resting_points,
    dao_reduce_sms_provider_priority,
)
from app.dao.services_dao import (
    dao_find_services_sending_to_tv_numbers,
    dao_find_services_with_high_failure_rates,
)
from app.dao.users_dao import delete_codes_older_created_more_than_a_day_ago
from app.letters.utils import generate_letter_pdf_filename
from app.models import (
    AnnualBilling,
    EmailBranding,
    Event,
    Job,
    Organisation,
    Service,
    User,
)
from app.notifications.process_notifications import send_notification_to_queue
from app.utils import get_london_midnight_in_utc


@notify_celery.task(name="run-scheduled-jobs")
@cronitor("run-scheduled-jobs")
def run_scheduled_jobs():
    try:
        for job in dao_set_scheduled_jobs_to_pending():
            process_job.apply_async([str(job.id)], queue=QueueNames.JOBS)
            current_app.logger.info("Job ID %s added to process job queue", job.id)
    except SQLAlchemyError:
        current_app.logger.exception("Failed to run scheduled jobs")
        raise


@notify_celery.task(name="delete-verify-codes")
def delete_verify_codes():
    try:
        start = datetime.utcnow()
        deleted = delete_codes_older_created_more_than_a_day_ago()
        current_app.logger.info(
            "Delete job started %s finished %s deleted %s verify codes", start, datetime.utcnow(), deleted
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete verify codes")
        raise


@notify_celery.task(name="delete-invitations")
def delete_invitations():
    try:
        start = datetime.utcnow()
        deleted_invites = delete_invitations_created_more_than_two_days_ago()
        deleted_invites += delete_org_invitations_created_more_than_two_days_ago()
        current_app.logger.info(
            "Delete job started %s finished %s deleted %s invitations", start, datetime.utcnow(), deleted_invites
        )
    except SQLAlchemyError:
        current_app.logger.exception("Failed to delete invitations")
        raise


@notify_celery.task(name="switch-current-sms-provider-on-slow-delivery")
def switch_current_sms_provider_on_slow_delivery():
    """
    Reduce provider's priority if at least 15% of notifications took more than 5 minutes to be delivered
    in the last ten minutes. If both providers are slow, don't do anything. If we changed the providers in the
    last ten minutes, then don't update them again either.
    """
    slow_delivery_notifications = is_delivery_slow_for_providers(
        created_within_minutes=15,
        delivered_within_minutes=5,
        threshold=0.15,
    )

    # only adjust if some values are true and some are false - ie, don't adjust if all providers are fast or
    # all providers are slow
    if len(set(slow_delivery_notifications.values())) != 1:
        for provider_name, is_slow in slow_delivery_notifications.items():
            if is_slow:
                current_app.logger.warning("Slow delivery notifications detected for provider %s", provider_name)
                dao_reduce_sms_provider_priority(provider_name, time_threshold=timedelta(minutes=10))


def _check_slow_text_message_delivery_reports_and_raise_error_if_needed(reports: list[SlowProviderDeliveryReport]):
    total_notifications = sum(report.total_notifications for report in reports)
    slow_notifications = sum(report.slow_notifications for report in reports)
    percent_slow_notifications = (slow_notifications / total_notifications) * 100

    # If over 10% of all text messages sent over the period have taken longer than 5 minutes to deliver, let's flag a
    # sentry error for us to investigate.
    if percent_slow_notifications >= 10:
        count = redis_store.incr(CacheKeys.NUMBER_OF_TIMES_OVER_SLOW_SMS_DELIVERY_THRESHOLD)

        # If this is the tenth consecutive time we've seen the threshold breached, then we log an error to Sentry.
        # This tells us that for at least 10 minutes we've seen delivery take longer than 5 minutes for >10% of
        # texts sent in the last 15 minutes (yes this is convoluted).
        #
        # Every minute, we check all the messages sent in the last 15 minutes. If more than 10% of those took >5
        # minutes to go from sending->delivered, then we consider that a breach for that minute. This could be triggered
        # in a number of different ways, for example:
        #
        # * 10% of messages taking >5 minutes to deliver, for 10 minutes consecutively.
        # * 100% of messages taking >5 minutes to deliver, for 3 minutes consecutively. For the following 7 minutes,
        #   assuming consistent throughput, the average will skew above 10% and continue to breach the threshold. On
        #   the tenth minute, even if all messages are now delivering quickly, we'll still probably log an error.
        #
        # In either case, it's worth investigating.
        #
        # By only checking for == 10, we don't log any further errors until we recover and then starting slowing down
        # again. This should mean that each instance of the error on Sentry actually deserves to be investigated as
        # a separate issue/potential incident.
        if count == 10:
            with sentry_sdk.push_scope() as scope:
                error_context = {
                    "Support runbook": (
                        "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#slow-sms-delivery"
                    ),
                    "Slow text messages - #": slow_notifications,
                    "Slow text messages - %": percent_slow_notifications,
                    "Total text messages": total_notifications,
                }

                for report in reports:
                    error_context[f"provider.{report.provider}.slow_ratio"] = report.slow_ratio
                    error_context[f"provider.{report.provider}.slow_notifications"] = report.slow_notifications
                    error_context[f"provider.{report.provider}.total_notifications"] = report.total_notifications

                scope.set_context("Slow SMS delivery", error_context)
                current_app.logger.error(
                    "Over 10% of text messages sent in the last 25 minutes have taken over 5 minutes to deliver."
                )

    else:
        redis_store.set(CacheKeys.NUMBER_OF_TIMES_OVER_SLOW_SMS_DELIVERY_THRESHOLD, 0)


@notify_celery.task(name="generate-sms-delivery-stats")
def generate_sms_delivery_stats():
    for delivery_interval in (1, 5, 10):
        providers_slow_delivery_reports = get_slow_text_message_delivery_reports_by_provider(
            created_within_minutes=15, delivered_within_minutes=delivery_interval
        )

        for report in providers_slow_delivery_reports:
            statsd_client.gauge(
                f"slow-delivery.{report.provider}.delivered-within-minutes.{delivery_interval}.ratio", report.slow_ratio
            )

        total_notifications = sum(report.total_notifications for report in providers_slow_delivery_reports)
        slow_notifications = sum(report.slow_notifications for report in providers_slow_delivery_reports)
        ratio_slow_notifications = slow_notifications / total_notifications

        statsd_client.gauge(
            f"slow-delivery.sms.delivered-within-minutes.{delivery_interval}.ratio", ratio_slow_notifications
        )

        # For the 5-minute delivery interval, let's check the percentage of all text messages sent that were slow.
        # TODO: delete this when we have a way to raise these alerts from eg grafana, prometheus, something else.
        if delivery_interval == 5 and current_app.is_prod:
            _check_slow_text_message_delivery_reports_and_raise_error_if_needed(providers_slow_delivery_reports)


@notify_celery.task(name="tend-providers-back-to-middle")
def tend_providers_back_to_middle():
    dao_adjust_provider_priority_back_to_resting_points()


@notify_celery.task(name="check-job-status")
def check_job_status():
    """
    every x minutes do this check
    select
    from jobs
    where job_status == 'in progress'
    and processing started between 30 and 35 minutes ago
    OR where the job_status == 'pending'
    and the job scheduled_for timestamp is between 30 and 35 minutes ago.
    if any results then
        update the job_status to 'error'
        process the rows in the csv that are missing (in another task) just do the check here.
    """
    thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
    thirty_five_minutes_ago = datetime.utcnow() - timedelta(minutes=35)

    incomplete_in_progress_jobs = Job.query.filter(
        Job.job_status == JOB_STATUS_IN_PROGRESS,
        between(Job.processing_started, thirty_five_minutes_ago, thirty_minutes_ago),
    )
    incomplete_pending_jobs = Job.query.filter(
        Job.job_status == JOB_STATUS_PENDING,
        Job.scheduled_for.isnot(None),
        between(Job.scheduled_for, thirty_five_minutes_ago, thirty_minutes_ago),
    )

    jobs_not_complete_after_30_minutes = (
        incomplete_in_progress_jobs.union(incomplete_pending_jobs)
        .order_by(Job.processing_started, Job.scheduled_for)
        .all()
    )

    # temporarily mark them as ERROR so that they don't get picked up by future check_job_status tasks
    # if they haven't been re-processed in time.
    job_ids = []
    for job in jobs_not_complete_after_30_minutes:
        job.job_status = JOB_STATUS_ERROR
        dao_update_job(job)
        job_ids.append(str(job.id))

    if job_ids:
        current_app.logger.info("Job(s) %s have not completed.", job_ids)
        process_incomplete_jobs.apply_async([job_ids], queue=QueueNames.JOBS)


@notify_celery.task(name="replay-created-notifications")
def replay_created_notifications():
    # if the notification has not be send after 1 hour, then try to resend.
    resend_created_notifications_older_than = 60 * 60
    for notification_type in (EMAIL_TYPE, SMS_TYPE):
        notifications_to_resend = notifications_not_yet_sent(resend_created_notifications_older_than, notification_type)

        if len(notifications_to_resend) > 0:
            current_app.logger.info(
                (
                    "Sending %(num)s %(type)s notifications to the delivery queue because the "
                    "notification status was created."
                ),
                dict(num=len(notifications_to_resend), type=notification_type),
            )

        for n in notifications_to_resend:
            send_notification_to_queue(notification=n)

    # if the letter has not be send after an hour, then create a zendesk ticket
    letters = letters_missing_from_sending_bucket(resend_created_notifications_older_than)

    if len(letters) > 0:
        current_app.logger.info(
            (
                "%(num)s letters were created over an hour ago, "
                "but do not have an updated_at timestamp or billable units.\n"
                "Creating app.celery.letters_pdf_tasks.create_letters tasks to upload letter to S3 "
                "and update notifications for the following notification ids:\n%(ids)s"
            ),
            dict(num=len(letters), ids=[x.id for x in letters]),
        )
        for letter in letters:
            get_pdf_for_templated_letter.apply_async([str(letter.id)], queue=QueueNames.CREATE_LETTERS_PDF)


@notify_celery.task(name="check-if-letters-still-pending-virus-check")
def check_if_letters_still_pending_virus_check():
    letters = []

    for letter in dao_precompiled_letters_still_pending_virus_check():
        # find letter in the scan bucket
        filename = generate_letter_pdf_filename(
            letter.reference, letter.created_at, ignore_folder=True, postage=letter.postage
        )

        if s3.file_exists(current_app.config["S3_BUCKET_LETTERS_SCAN"], filename):
            current_app.logger.warning(
                "Letter id %s got stuck in pending-virus-check. Sending off for scan again.", letter.id
            )
            notify_celery.send_task(
                name=TaskNames.SCAN_FILE,
                kwargs={"filename": filename},
                queue=QueueNames.ANTIVIRUS,
            )
        else:
            letters.append(letter)

    if len(letters) > 0:
        letter_ids = [(str(letter.id), letter.reference) for letter in letters]

        msg = f"""{len(letters)} precompiled letters have been pending-virus-check for over 10 minutes
            We couldn't find them in the scan bucket. We'll need to find out where the files are and kick them off
            again or move them to technical failure.

            Notifications: {sorted(letter_ids)}"""

        if current_app.should_send_zendesk_alerts:
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] Letters still pending virus check",
                message=msg,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                notify_ticket_type=NotifyTicketType.TECHNICAL,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
            current_app.logger.error(
                "Letters still pending virus check",
                extra=dict(number_of_letters=len(letters), notification_ids=sorted(letter_ids)),
            )


@notify_celery.task(name="check-if-letters-still-in-created")
def check_if_letters_still_in_created():
    letters = dao_old_letters_with_created_status()

    if len(letters) > 0:
        msg = (
            f"{len(letters)} letters were created before 17.30 yesterday and still have 'created' status. "
            "Follow runbook to resolve: "
            "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook"
            "#deal-with-letters-still-in-created."
        )

        if current_app.should_send_zendesk_alerts:
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] Letters still in 'created' status",
                message=msg,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                notify_ticket_type=NotifyTicketType.TECHNICAL,
                ticket_categories=["notify_letters"],
            )
            zendesk_client.send_ticket_to_zendesk(ticket)
            current_app.logger.error(
                "%s letters created before 17:30 yesterday still have 'created' status",
                len(letters),
            )


@notify_celery.task(name="check-for-missing-rows-in-completed-jobs")
def check_for_missing_rows_in_completed_jobs():
    jobs = find_jobs_with_missing_rows()
    for job in jobs:
        recipient_csv, template, sender_id = get_recipient_csv_and_template_and_sender_id(job)
        missing_rows = find_missing_row_for_job(job.id, job.notification_count)
        for row_to_process in missing_rows:
            row = recipient_csv[row_to_process.missing_row]
            current_app.logger.info("Processing missing row: %s for job: %s", row_to_process.missing_row, job.id)
            process_row(row, template, job, job.service, sender_id=sender_id)


@notify_celery.task(name="check-for-services-with-high-failure-rates-or-sending-to-tv-numbers")
def check_for_services_with_high_failure_rates_or_sending_to_tv_numbers():
    start_date = datetime.utcnow() - timedelta(days=1)
    end_date = datetime.utcnow()
    message = ""

    services_with_failures = dao_find_services_with_high_failure_rates(start_date=start_date, end_date=end_date)
    services_sending_to_tv_numbers = dao_find_services_sending_to_tv_numbers(start_date=start_date, end_date=end_date)

    if services_with_failures:
        message += "{} service(s) have had high permanent-failure rates for sms messages in last 24 hours:\n".format(
            len(services_with_failures)
        )
        for service in services_with_failures:
            service_dashboard = "{}/services/{}".format(
                current_app.config["ADMIN_BASE_URL"],
                str(service.service_id),
            )
            message += "service: {} failure rate: {},\n".format(service_dashboard, service.permanent_failure_rate)

        current_app.logger.error(
            "%s services have had a high permanent-failure rate for text messages in the last 24 hours.",
            len(services_with_failures),
            extra=dict(service_ids=[service.service_id for service in services_with_failures]),
        )

    elif services_sending_to_tv_numbers:
        message += "{} service(s) have sent over 500 sms messages to tv numbers in last 24 hours:\n".format(
            len(services_sending_to_tv_numbers)
        )
        for service in services_sending_to_tv_numbers:
            service_dashboard = "{}/services/{}".format(
                current_app.config["ADMIN_BASE_URL"],
                str(service.service_id),
            )
            message += "service: {} count of sms to tv numbers: {},\n".format(
                service_dashboard, service.notification_count
            )

        current_app.logger.error(
            "%s services have sent over 500 text messages to tv numbers in the last 24 hours.",
            len(services_sending_to_tv_numbers),
            extra=dict(
                service_ids_and_number_sent={
                    service.service_id: service.notification_count for service in services_sending_to_tv_numbers
                }
            ),
        )

    if services_with_failures or services_sending_to_tv_numbers:
        if current_app.should_send_zendesk_alerts:
            message += (
                "\nYou can find instructions for this ticket in our manual:\n"
                "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#deal-with-services-with-high-failure-rates-or-sending-sms-to-tv-numbers"  # noqa
            )  # noqa
            ticket = NotifySupportTicket(
                subject=f"[{current_app.config['NOTIFY_ENVIRONMENT']}] High failure rates for sms spotted for services",
                message=message,
                ticket_type=NotifySupportTicket.TYPE_INCIDENT,
                notify_ticket_type=NotifyTicketType.TECHNICAL,
            )
            zendesk_client.send_ticket_to_zendesk(ticket)


@notify_celery.task(name="delete-old-records-from-events-table")
@cronitor("delete-old-records-from-events-table")
def delete_old_records_from_events_table():
    delete_events_before = datetime.utcnow() - timedelta(weeks=52)
    event_query = Event.query.filter(Event.created_at < delete_events_before)

    deleted_count = event_query.delete()

    current_app.logger.info("Deleted %s historical events from before %s.", deleted_count, delete_events_before)

    db.session.commit()


@notify_celery.task(name="zendesk-new-email-branding-report")
def zendesk_new_email_branding_report():
    # make sure we convert to BST as in summer this'll run at 23:30 UTC
    previous_weekday = convert_utc_to_bst(datetime.utcnow()).date() - timedelta(days=1)

    # If yesterday is a Saturday or Sunday, adjust back to the Friday
    if previous_weekday.isoweekday() in {6, 7}:
        previous_weekday -= timedelta(days=(previous_weekday.isoweekday() - 5))

    previous_weekday_midnight = get_london_midnight_in_utc(previous_weekday)

    new_email_brands = (
        EmailBranding.query.join(Organisation, isouter=True)
        .join(User, User.id == EmailBranding.created_by, isouter=True)
        .filter(
            EmailBranding.created_at >= previous_weekday_midnight,
            User.platform_admin.is_(False),
        )
        .order_by(EmailBranding.created_at)
        .all()
    )

    current_app.logger.info("%s new email brands to review since %s.", len(new_email_brands), previous_weekday)

    if not new_email_brands:
        return

    brands_by_organisation = defaultdict(list)
    brands_with_no_organisation = []
    for new_brand in new_email_brands:
        if not new_brand.organisations:
            brands_with_no_organisation.append(new_brand)

        else:
            for organisation in new_brand.organisations:
                brands_by_organisation[organisation].append(new_brand)

    with open("templates/tasks/scheduled_tasks/new_email_brandings.html") as template_file:
        template = jinja2.Template(template_file.read())

    message = template.render(
        domain=current_app.config["ADMIN_BASE_URL"],
        yesterday=previous_weekday.strftime("%A %-d %B %Y"),
        brands_by_organisation=brands_by_organisation,
        brands_with_no_organisation=brands_with_no_organisation,
    )

    if current_app.should_send_zendesk_alerts:
        ticket = NotifySupportTicket(
            subject="Review new email brandings",
            message=message,
            ticket_type=NotifySupportTicket.TYPE_TASK,
            notify_ticket_type=NotifyTicketType.NON_TECHNICAL,
            ticket_categories=["notify_no_ticket_category"],
            message_as_html=True,
        )
        zendesk_client.send_ticket_to_zendesk(ticket)


@notify_celery.task(name="check-for-low-available-inbound-sms-numbers")
@cronitor("check-for-low-available-inbound-sms-numbers")
def check_for_low_available_inbound_sms_numbers():
    if not current_app.should_send_zendesk_alerts:
        current_app.logger.info("Skipping report run on in %s", current_app.config["NOTIFY_ENVIRONMENT"])
        return

    num_available_inbound_numbers = len(dao_get_available_inbound_numbers())
    current_app.logger.info("There are %s available inbound SMS numbers.", num_available_inbound_numbers)
    if num_available_inbound_numbers > current_app.config["LOW_INBOUND_SMS_NUMBER_THRESHOLD"]:
        return

    message = (
        f"There are only {num_available_inbound_numbers} inbound SMS numbers currently available for services.\n\n"
        "Request more from our provider (MMG) and load them into the database.\n\n"
        "Follow the guidance here: "
        "https://github.com/alphagov/notifications-manuals/wiki/Support-Runbook#add-new-inbound-sms-numbers"
    )

    ticket = NotifySupportTicket(
        subject="Request more inbound SMS numbers",
        message=message,
        ticket_type=NotifySupportTicket.TYPE_TASK,
        notify_ticket_type=NotifyTicketType.TECHNICAL,
        ticket_categories=["notify_no_ticket_category"],
    )
    zendesk_client.send_ticket_to_zendesk(ticket)


@notify_celery.task(name="weekly-dwp-report")
def weekly_dwp_report():
    report_config = current_app.config["ZENDESK_REPORTING"].get("weekly-dwp-report")

    if not current_app.should_send_zendesk_alerts:
        current_app.logger.info("Skipping DWP report run in %s", current_app.config["NOTIFY_ENVIRONMENT"])
        return

    if (
        not report_config
        or not isinstance(report_config, dict)
        or not report_config.get("query")
        or not report_config.get("ticket_id")
    ):
        current_app.logger.info("Skipping DWP report run - invalid configuration.")
        return

    attachments = []
    for csv_name, query in report_config["query"].items():
        result = db.session.execute(query)
        headers = result.keys()
        rows = result.fetchall()

        csv_data = io.StringIO()
        csv_writer = csv.DictWriter(csv_data, fieldnames=headers, dialect="excel")
        csv_writer.writeheader()

        for row in rows:
            csv_writer.writerow(row._asdict())

        csv_data.seek(0)

        attachments.append(NotifySupportTicketAttachment(filename=csv_name, filedata=csv_data, content_type="text/csv"))

    zendesk_client.update_ticket(
        report_config["ticket_id"],
        status=NotifySupportTicketStatus.PENDING,
        comment=NotifySupportTicketComment(
            body="Please find attached your weekly report.",
            attachments=attachments,
        ),
        due_at=convert_utc_to_bst(datetime.utcnow() + timedelta(days=7, hours=3, minutes=10)),
    )


@notify_celery.task(bind=True, name="change-dvla-password", max_retries=3, default_retry_delay=60)
def change_dvla_password(self):
    try:
        dvla_client.change_password()
    except LockError:
        # some other task is currently changing the password. let that process handle it and quietly exit
        current_app.logger.info("change-dvla-password lock held by other process, doing nothing")
    except DvlaRetryableException:
        current_app.logger.info("change-dvla-password DvlaRetryableException - retrying")
        self.retry()


@notify_celery.task(bind=True, name="change-dvla-api-key", max_retries=3, default_retry_delay=60)
def change_dvla_api_key(self):
    try:
        dvla_client.change_api_key()
    except LockError:
        # some other task is currently changing the api key. let that process handle it and quietly exit
        current_app.logger.info("change-dvla-api-key lock held by other process, doing nothing")
    except DvlaRetryableException:
        current_app.logger.info("change-dvla-api-key DvlaRetryableException - retrying")
        self.retry()


def populate_annual_billing(year, missing_services_only):
    """
    Add or update annual billing with free allowance defaults for all active services.
    The default free allowances are stored in the DB in a table called `default_annual_allowance`.

    If missing_services_only is true then only add rows for services that do not have annual billing for that year yet.
    This is useful to prevent overriding any services that have a free allowance that is not the default.

    If missing_services_only is false then add or update annual billing for all active services.
    This is useful to ensure all services start the new year with the correct annual billing.
    """
    if missing_services_only:
        active_services = (
            Service.query.filter(Service.active)
            .outerjoin(
                AnnualBilling, and_(Service.id == AnnualBilling.service_id, AnnualBilling.financial_year_start == year)
            )
            .filter(AnnualBilling.id == None)  # noqa
            .all()
        )
    else:
        active_services = Service.query.filter(Service.active).all()

    for service in active_services:
        set_default_free_allowance_for_service(service, year)


@notify_celery.task(name="run-populate-annual-billing")
@cronitor("run-populate-annual-billing")
def run_populate_annual_billing():
    year = get_current_financial_year_start_year()
    populate_annual_billing(year=year, missing_services_only=True)
