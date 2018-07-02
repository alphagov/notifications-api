platform_stats_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "platform stats request schema",
    "type": "object",
    "title": "Platform stats request",
    "properties": {
        "start_date": {"type": ["string", "null"], "format": "date"},
        "end_date": {"type": ["string", "null"], "format": "date"},
    }
}
