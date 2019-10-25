send_pdf_letter_request = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "description": "POST send uploaded pdf letter",
    "type": "object",
    "title": "Send an uploaded pdf letter",
    "properties": {
        "postage": {"enum": ["first", "second"]},
        "filename": {"type": "string"},
        "created_by": {"type": "string"},
        "file_id": {"type": "string"},
    },

    "required": ["postage", "filename", "created_by", "file_id"]
}
