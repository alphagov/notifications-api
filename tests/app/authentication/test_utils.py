from app.authentication.utils import generate_secret, get_secret


def test_secret_is_signed_and_can_be_read_again(notify_api):
    with notify_api.test_request_context():
        signed_secret = generate_secret('some_uuid')
        assert signed_secret != 'some_uuid'
        assert 'some_uuid' == get_secret(signed_secret)
