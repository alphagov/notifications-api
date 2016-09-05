import os

from flask import json
import jsonschema


def validate(json_string, schema_filename):
    schema_dir = os.path.join(os.path.dirname(__file__), 'schemas')
    resolver = jsonschema.RefResolver('file://' + schema_dir + '/', None)
    with open(os.path.join(schema_dir, schema_filename)) as schema:
        jsonschema.validate(
            json.loads(json_string),
            json.load(schema),
            format_checker=jsonschema.FormatChecker(),
            resolver=resolver
        )
