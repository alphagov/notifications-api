import json
import uuid

import pytest
from jsonschema import ValidationError

from app.letters.letter_schemas import letter_job_ids
from app.schema_validation import validate


def test_letter_job_id_retuns_400_if_array_is_empty():
    with pytest.raises(ValidationError) as e:
        validate({"job_ids": []}, letter_job_ids)
    error = json.loads(str(e.value))
    assert len(error.keys()) == 2
    assert error.get('errors')[0]['message'] == 'job_ids [] is too short'


def test_letter_job_id_retuns_400_if_array_doesnot_contain_uuids():
    with pytest.raises(ValidationError) as e:
        validate({"job_ids": ["1", "2"]}, letter_job_ids)
    error = json.loads(str(e.value))
    assert len(error.keys()) == 2
    assert error.get('errors')[0]['message'] == 'job_ids is not a valid UUID'


def test_letter_job():
    ids_ = {"job_ids": [str(uuid.uuid4()), str(uuid.uuid4())]}
    j = validate(ids_, letter_job_ids)
    assert j == ids_
