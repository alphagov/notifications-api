import json
from jsonschema import Draft4Validator, ValidationError


def validate(json_to_validate, schema):
    validator = Draft4Validator(schema)
    errors = list(validator.iter_errors(json_to_validate))
    if errors.__len__() > 0:
        raise ValidationError(build_error_message(errors, schema))
    return json_to_validate


def build_error_message(errors, schema):
    fields = []
    for e in errors:
        field = "'{}' {}".format(e.path[0], e.schema.get('validationMessage')) if e.schema.get(
            'validationMessage') else e.message
        fields.append(field)
    message = {
        "code": "1001",
        "message": "Validation error occurred - {}".format(schema['title']),
        "link": "link to error documentation (not yet implemented)",
        "fields": fields
    }

    return json.dumps(message)
