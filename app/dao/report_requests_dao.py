from uuid import UUID

from app import db
from app.dao.dao_utils import autocommit
from app.models import ReportRequest


@autocommit
def dao_create_report_request(report_request: ReportRequest):
    db.session.add(report_request)


def dao_get_report_request_by_id(service_id: UUID, report_id: UUID) -> ReportRequest:
    return ReportRequest.query.filter_by(service_id=service_id, id=report_id).one()
