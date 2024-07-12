send_pdf_letter_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST send uploaded pdf letter",
    "type": "object",
    "title": "Send an uploaded pdf letter",
    "properties": {
        "postage": {"type": "string", "format": "postage_including_international"},
        "filename": {"type": "string"},
        "created_by": {"type": "string"},
        "file_id": {"type": "string"},
        "recipient_address": {"type": "string"},
    },
    "required": ["postage", "filename", "created_by", "file_id", "recipient_address"],
}
