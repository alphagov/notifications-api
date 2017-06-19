import json
import uuid

import pytest
from jsonschema import ValidationError

from app.schema_validation import validate
from app.service.service_inbound_api_schema import service_inbound_api


def test_service_inbound_api_schema_validates():
    under_test = {"url": "https://some_url.for_service",
                  "bearer_token": "something_ten_chars",
                  "updated_by_id": str(uuid.uuid4())
                  }

    validated = validate(under_test, service_inbound_api)
    assert validated == under_test


@pytest.mark.parametrize("url", ["not a url", "https not a url", "http://valid.com"])
def test_service_inbound_api_schema_errors_for_url_not_valid_url(url):
    under_test = {"url": url,
                  "bearer_token": "something_ten_chars",
                  "updated_by_id": str(uuid.uuid4())
                  }

    with pytest.raises(ValidationError) as e:
        validate(under_test, service_inbound_api)
    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 1
    assert errors[0]['message'] == "url is not a valid https url"


def test_service_inbound_api_schema_bearer_token_under_ten_char():
    under_test = {"url": "https://some_url.for_service",
                  "bearer_token": "shorty",
                  "updated_by_id": str(uuid.uuid4())
                  }

    with pytest.raises(ValidationError) as e:
        validate(under_test, service_inbound_api)
    errors = json.loads(str(e.value)).get('errors')
    assert len(errors) == 1
    assert errors[0]['message'] == "bearer_token shorty is too short"
