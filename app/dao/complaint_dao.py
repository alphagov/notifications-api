from app import db
from app.dao.dao_utils import transactional
from app.models import Complaint


@transactional
def save_complaint(complaint):
    db.session.add(complaint)


def fetch_complaints_by_service(service_id):
    return Complaint.query.filter_by(service_id=service_id).all()
