import os

from flask import json
import jsonschema

def validate(json_string, schema_filename):
    resolver = jsonschema.RefResolver('file://' + os.path.dirname(__file__) + '/', None)
    with open(os.path.join(os.path.dirname(__file__), schema_filename)) as schema:
        jsonschema.validate(
            json.loads(json_string),
            json.load(schema),
            format_checker=jsonschema.FormatChecker(),
            resolver=resolver
        )
