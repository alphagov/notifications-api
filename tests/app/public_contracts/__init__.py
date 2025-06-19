from flask import json
from jsonschema import Draft7Validator


def return_json_from_response(response):
    return json.loads(response.get_data(as_text=True))


def validate(json_to_validate, schema):
    validator = Draft7Validator(schema)
    validator.validate(json_to_validate, schema)
