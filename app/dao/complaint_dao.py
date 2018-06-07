from app import db
from app.dao.dao_utils import transactional
from app.models import Complaint


@transactional
def save_complaint(complaint):
    db.session.add(complaint)


def fetch_complaints_by_service(service_id):
    return Complaint.query.filter_by(service_id=service_id).all()


def fetch_count_of_complaints(start_date, end_date):
    return Complaint.count.filter(Complaint.created_at >= start_date, Complaint.created_at < end_date)
