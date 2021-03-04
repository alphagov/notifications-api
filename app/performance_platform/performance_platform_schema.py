performance_platform_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Performance platform request schema",
    "type": "object",
    "title": "Performance platform request",
    "properties": {
        "start_date": {"type": ["string", "null"], "format": "date"},
        "end_date": {"type": ["string", "null"], "format": "date"},
    }
}
