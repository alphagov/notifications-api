from datetime import datetime, timedelta
from app.models import (Notification,
                        Rate,
                        NOTIFICATION_CREATED,
                        NOTIFICATION_TECHNICAL_FAILURE,
                        KEY_TYPE_TEST,
                        LetterRate,
                        FactBilling,
                        Service,
                        LETTER_TYPE, SMS_TYPE)
from app import db
from sqlalchemy import func, desc, case
from app.dao.dao_utils import transactional
from notifications_utils.statsd_decorators import statsd
from app import notify_celery


def get_rate(non_letter_rates, letter_rates, notification_type, date, crown=None, rate_multiplier=None):

    if notification_type == LETTER_TYPE:
        return next(r[3] for r in letter_rates if date > r[0] and crown == r[1] and rate_multiplier == r[2])
    elif notification_type == SMS_TYPE:
        return next(r[2] for r in non_letter_rates if notification_type == r[0] and date > r[1])
    else:
        return 0


@notify_celery.task(name="create-nightly-billing")
@statsd(namespace="tasks")
@transactional
def create_nightly_billing(day_start=None):
    if day_start is None:
        day_start = datetime.date(datetime.utcnow()) - timedelta(days=3)   # Nightly jobs consolidating last 3 days
        # Task to be run after mid-night

    non_letter_rates = [(r.notification_type, r.valid_from, r.rate) for r in
                        Rate.query.order_by(desc(Rate.valid_from)).all()]
    letter_rates = [(r.start_date, r.crown, r.sheet_count, r.rate) for r in
                    LetterRate.query.order_by(desc(LetterRate.start_date)).all()]

    transit_data = db.session.query(
        func.date_trunc('day', Notification.created_at).label('day_created'),
        Notification.template_id,
        Notification.service_id,
        Notification.notification_type,
        func.coalesce(Notification.sent_by,
                      case(
                          [
                              (Notification.notification_type == 'letter', 'dvla'),
                              (Notification.notification_type == 'sms', 'unknown'),
                              (Notification.notification_type == 'email', 'ses')
                          ]),
                      ).label('sent_by'),
        func.coalesce(Notification.rate_multiplier, 1).label('rate_multiplier'),
        func.coalesce(Notification.international, False).label('international'),
        func.sum(Notification.billable_units).label('billable_units'),
        func.count().label('notifications_sent'),
        Service.crown,
    ).filter(
        Notification.status != NOTIFICATION_CREATED,        # at created status, provider information is not available
        Notification.status != NOTIFICATION_TECHNICAL_FAILURE,
        Notification.key_type != KEY_TYPE_TEST,
        Notification.created_at >= day_start
    ).group_by(
        'day_created',
        Notification.template_id,
        Notification.service_id,
        Notification.notification_type,
        'sent_by',
        Notification.rate_multiplier,
        Notification.international,
        Service.crown
    ).join(
        Service
    ).order_by(
        'day_created'
    ).all()

    for data in transit_data:
        update_count = FactBilling.query.filter(
            FactBilling.bst_date == data.day_created,
            FactBilling.template_id == data.template_id,
            FactBilling.provider == data.sent_by,  # This could be zero - this is a bug that needs to be fixed.
            FactBilling.rate_multiplier == data.rate_multiplier,
            FactBilling.international == data.international,
        ).update(
            {"notifications_sent": data.notifications_sent,
             "billable_units": data.billable_units},
            synchronize_session=False)
        if update_count == 0:
            billing_record = FactBilling(
                bst_date=data.day_created,
                template_id=data.template_id,
                service_id=data.service_id,
                notification_type=data.notification_type,
                provider=data.sent_by,
                rate_multiplier=data.rate_multiplier,
                international=data.international,
                billable_units=data.billable_units,
                notifications_sent=data.notifications_sent,
                rate=get_rate(non_letter_rates,
                              letter_rates,
                              data.notification_type,
                              data.day_created,
                              data.crown,
                              data.rate_multiplier)
            )
            db.session.add(billing_record)
