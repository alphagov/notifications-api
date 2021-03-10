from flask import Blueprint, jsonify, request

from app.dao.events_dao import dao_create_event
from app.errors import register_errors
from app.schemas import event_schema

events = Blueprint('events', __name__, url_prefix='/events')
register_errors(events)


@events.route('', methods=['POST'])
def create_event():
    data = request.get_json()
    event = event_schema.load(data).data
    dao_create_event(event)
    return jsonify(data=event_schema.dump(event).data), 201
