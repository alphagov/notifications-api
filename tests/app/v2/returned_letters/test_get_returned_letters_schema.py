import json

import pytest
from jsonschema import ValidationError

from app.schema_validation import validate
from app.v2.returned_letters.get_returned_letters_schema import get_returned_letters_request


@pytest.mark.parametrize(
    "invalid_args, expected_error",
    [
        ({}, {"error": "ValidationError", "message": "report_date is a required property"}),
        ({"report_date": "12-06-26"}, {"error": "ValidationError", "message": "report_date 12-06-26 is not a date"}),
        (
            {"report_date": "2026/06/12"},
            {"error": "ValidationError", "message": "report_date 2026/06/12 is not a date"},
        ),
        (
            {"report_date": "12-06-2026 10:30:45"},
            {"error": "ValidationError", "message": "report_date 12-06-2026 10:30:45 is not a date"},
        ),
    ],
)
def test_v2_get_returned_letters_report_date_validation(invalid_args, expected_error):
    # test that validation enforces YYYY-MM-DD format for report_date
    with pytest.raises(ValidationError) as e:
        validate(invalid_args, get_returned_letters_request)
    error = json.loads(str(e.value))
    assert error.get("status_code") == 400
    assert error.get("errors")[0] == expected_error
