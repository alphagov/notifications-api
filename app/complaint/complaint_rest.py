from flask import Blueprint, jsonify
from sqlalchemy import desc

from app.errors import register_errors
from app.models import Complaint

complaint_blueprint = Blueprint('complaint', __name__, url_prefix='/complaint')

register_errors(complaint_blueprint)


@complaint_blueprint.route('', methods=['GET'])
def get_all_complaints():
    complaints = Complaint.query.order_by(desc(Complaint.created_at)).all()

    return jsonify([x.serialize() for x in complaints]), 200
