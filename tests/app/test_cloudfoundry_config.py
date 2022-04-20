import json
import os

import pytest

from app.cloudfoundry_config import extract_cloudfoundry_config


@pytest.fixture
def vcap_services():
    return {
        'postgres': [{
            'credentials': {
                'uri': 'postgres uri'
            }
        }],
        'redis': [{
            'credentials': {
                'uri': 'redis uri'
            }
        }],
        'user-provided': []
    }


def test_extract_cloudfoundry_config_populates_other_vars(os_environ, vcap_services):
    os.environ['VCAP_SERVICES'] = json.dumps(vcap_services)
    extract_cloudfoundry_config()

    assert os.environ['SQLALCHEMY_DATABASE_URI'] == 'postgresql uri'
    assert os.environ['REDIS_URL'] == 'redis uri'
