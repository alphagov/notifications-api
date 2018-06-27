from datetime import timedelta

from sqlalchemy import desc

from app import db
from app.dao.dao_utils import transactional
from app.models import Complaint
from app.utils import get_london_midnight_in_utc


@transactional
def save_complaint(complaint):
    db.session.add(complaint)


def fetch_complaints_by_service(service_id):
    return Complaint.query.filter_by(service_id=service_id).order_by(desc(Complaint.created_at)).all()


def fetch_count_of_complaints(start_date, end_date):
    start_date = get_london_midnight_in_utc(start_date)
    end_date = get_london_midnight_in_utc(end_date + timedelta(days=1))

    return Complaint.query.filter(Complaint.created_at >= start_date, Complaint.created_at < end_date).count()
