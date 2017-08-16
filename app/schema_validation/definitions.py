"""
Definitions are intended for schema definitions that are not likely to change from version to version.
If the definition is specific to a version put it in a definition file in the version package
"""

uuid = {
    "type": "string",
    "pattern": "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$",
    "validationMessage": "is not a valid UUID",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented"
}


personalisation = {
    "type": "object",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented"
}


letter_personalisation = dict(personalisation, required=["address_line_1", "address_line_2", "postcode"])


https_url = {
    "type": "string",
    "format": "uri",
    "pattern": "^https.*",
    "validationMessage": "is not a valid https url",
    "code": "1001",  # yet to be implemented
    "link": "link to our error documentation not yet implemented"
}
