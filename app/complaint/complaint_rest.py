from datetime import datetime

from flask import Blueprint, jsonify, request

from app.complaint.complaint_schema import complaint_count_request
from app.dao.complaint_dao import fetch_count_of_complaints, fetch_paginated_complaints
from app.errors import register_errors
from app.schema_validation import validate
from app.utils import pagination_links

complaint_blueprint = Blueprint('complaint', __name__, url_prefix='/complaint')

register_errors(complaint_blueprint)


@complaint_blueprint.route('', methods=['GET'])
def get_all_complaints():
    page = int(request.args.get('page', 1))
    pagination = fetch_paginated_complaints(page=page)

    return jsonify(
        complaints=[x.serialize() for x in pagination.items],
        links=pagination_links(
            pagination,
            '.get_all_complaints',
            **request.args.to_dict()
        )
    ), 200


@complaint_blueprint.route('/count-by-date-range', methods=['GET'])
def get_complaint_count():
    if request.args:
        validate(request.args, complaint_count_request)

    # If start and end date are not set, we are expecting today's stats.
    today = str(datetime.utcnow().date())

    start_date = datetime.strptime(request.args.get('start_date', today), '%Y-%m-%d').date()
    end_date = datetime.strptime(request.args.get('end_date', today), '%Y-%m-%d').date()
    count_of_complaints = fetch_count_of_complaints(start_date=start_date, end_date=end_date)

    return jsonify(count_of_complaints), 200
