from sqlalchemy import func

from app import db
from app.dao.date_util import get_month_start_and_end_date_in_utc
from app.models import FactBilling
from app.utils import convert_utc_to_bst


def fetch_annual_billing_by_month(service_id, billing_month, notification_type):
    billing_month_in_bst = convert_utc_to_bst(billing_month)
    start_date, end_date = get_month_start_and_end_date_in_utc(billing_month_in_bst)

    monthly_data = db.session.query(
        func.sum(FactBilling.notifications_sent).label('notifications_sent'),
        func.sum(FactBilling.billable_units).label('billing_units'),
        FactBilling.service_id,
        FactBilling.notification_type,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).filter(
        FactBilling.notification_type == notification_type,
        FactBilling.service_id == service_id,
        FactBilling.bst_date >= start_date,
        FactBilling.bst_date <= end_date
    ).group_by(
        FactBilling.service_id,
        FactBilling.notification_type,
        FactBilling.rate,
        FactBilling.rate_multiplier,
        FactBilling.international
    ).all()

    return monthly_data, start_date
