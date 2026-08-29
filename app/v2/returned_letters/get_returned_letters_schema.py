get_returned_letters_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "schema for retrieving returned letters for a service",
    "title": "GET v2/returned-letters",
    "type": "object",
    "properties": {"report_date": {"type": "string", "format": "date"}},
    "required": ["report_date"],
    "additionalProperties": False,
}
