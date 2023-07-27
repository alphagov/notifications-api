from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.dao.events_dao import dao_create_event
from app.errors import register_errors
from app.models import Event, EventSerializer
from app.openapi import UnauthorizedResponse

events = APIBlueprint(
    "events",
    __name__,
    url_prefix="/events",
    abp_tags=[Tag(name="events")],
    abp_security=[{"admin": []}],
    abp_responses={"401": UnauthorizedResponse},
)
register_errors(events)


class CreateEvent(BaseModel):
    event_type: str = Field(max_length=255)
    data: dict


class EventResponse(BaseModel):
    data: EventSerializer


@events.post("", responses={"201": EventResponse})
def create_event(body: CreateEvent):
    event = Event(event_type=body.event_type, data=body.data)
    dao_create_event(event)
    event_response = EventSerializer.from_orm(event)
    return EventResponse(data=event_response).json(), 201
