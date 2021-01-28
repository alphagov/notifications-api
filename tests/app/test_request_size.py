import pytest
import json

@pytest.mark.parametrize('endpoint, max_content_length, expected_status_code', [
    ("/_status", 5*1024*1024, 413),
    ("/provider-details", 5*1024*1024, 413),
    ("/v2/notifications/email", 5*1024*1024, 413),

    ("/_status", None, 200),
    ("/provider-details", None, 405),
    ("/v2/notifications/email", None, 401),
])
def test_request_status_when_content_length_is_set(
    notify_api,
    sample_email_template_with_placeholders,
    mocker,
    endpoint,
    max_content_length,
    expected_status_code):

    notify_api.config['MAX_CONTENT_LENGTH'] = max_content_length
    large_name = "J" * (max_content_length or 1 + 1)
    data = {
        'email_address': 'ok@ok.com',
        'template_id': str(sample_email_template_with_placeholders.id),
        'personalisation': {
            'name': large_name
        }
    }
    with notify_api.test_client() as client:
        response = client.post(
            path=endpoint,
            data=json.dumps(data),
            headers=[('Content-Type', 'application/json')])

        assert response.status_code == expected_status_code
