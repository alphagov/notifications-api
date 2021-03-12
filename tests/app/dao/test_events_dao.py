
from app.dao.events_dao import dao_create_event
from app.models import Event


def test_create_event(notify_db, notify_db_session):
    assert Event.query.count() == 0
    data = {
        'event_type': 'sucessful_login',
        'data': {'something': 'random', 'in_fact': 'could be anything'}
    }

    event = Event(**data)
    dao_create_event(event)

    assert Event.query.count() == 1
    event_from_db = Event.query.first()
    assert event == event_from_db
