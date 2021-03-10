performance_dashboard_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "Performance dashboard request schema",
    "type": "object",
    "title": "Performance dashboard request",
    "properties": {
        "start_date": {"type": ["string", "null"], "format": "date"},
        "end_date": {"type": ["string", "null"], "format": "date"},
    }
}
