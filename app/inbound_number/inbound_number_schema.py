from app.schema_validation.definitions import uuid

add_inbound_number_to_service_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST add service inbound number",
    "type": "object",
    "title": "Assign inbound number to service",
    "properties": {"inbound_number_id": uuid},
}
