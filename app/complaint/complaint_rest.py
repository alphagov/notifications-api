from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import desc

from app.complaint.complaint_schema import complaint_count_request
from app.dao.complaint_dao import fetch_count_of_complaints
from app.errors import register_errors
from app.models import Complaint
from app.schema_validation import validate

complaint_blueprint = Blueprint('complaint', __name__, url_prefix='/complaint')

register_errors(complaint_blueprint)


@complaint_blueprint.route('', methods=['GET'])
def get_all_complaints():
    complaints = Complaint.query.order_by(desc(Complaint.created_at)).all()

    return jsonify([x.serialize() for x in complaints]), 200


@complaint_blueprint.route('/total-per-day', methods=['GET'])
def get_complaint_count():
    request_json = request.args.to_dict
    start_date = None
    end_date = None
    if request_json:
        validate(request_json, complaint_count_request)
        start_date = request_json.get('start_date', None)
        end_date = request_json.get('end_date', None)
    if not start_date:
        start_date = datetime.utcnow().date()
    if not end_date:
        end_date = datetime.utcnow().date()

    count_of_complaints = fetch_count_of_complaints(start_date=start_date, end_date=end_date)

    return jsonify(count_of_complaints), 200
