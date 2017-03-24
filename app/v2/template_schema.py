from app.schema_validation.definitions import uuid

# this may belong in a templates module
template = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "template schema",
    "type": "object",
    "title": "notification content",
    "properties": {
        "id": uuid,
        "version": {"type": "integer"},
        "uri": {"type": "string", "format": "uri"}
    },
    "required": ["id", "version", "uri"]
}
