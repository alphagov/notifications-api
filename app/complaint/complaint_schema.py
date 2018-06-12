
complaint_count_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "complaint count request schema",
    "type": "object",
    "title": "Complaint count request",
    "properties": {
        "start_date": {"type": ["string", "null"], "format": "date"},
        "end_date": {"type": ["string", "null"], "format": "date"},
    }
}
