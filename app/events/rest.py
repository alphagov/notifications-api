from flask import (
    Blueprint,
    jsonify,
    request
)

from app.errors import (
    register_errors,
    InvalidData
)

from app.schemas import event_schema
from app.dao.events_dao import dao_create_event

events = Blueprint('events', __name__, url_prefix='/events')
register_errors(events)


@events.route('', methods=['POST'])
def create_event():
    data = request.get_json()
    event, errors = event_schema.load(data)
    if errors:
        raise InvalidData(errors, status_code=400)
    dao_create_event(event)
    return jsonify(data=event_schema.dump(event).data), 201
