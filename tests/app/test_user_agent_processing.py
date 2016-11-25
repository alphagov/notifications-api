from app import process_user_agent


def test_can_process_notify_api_user_agent():
    assert "notify-api-python-client.3-0-0" == process_user_agent("NOTIFY-API-PYTHON-CLIENT/3.0.0")


def test_can_handle_non_notify_api_user_agent():
    assert "non-notify-user-agent" == process_user_agent("Mozilla/5.0 (iPad; U; CPU OS 3_2_1 like Mac OS X; en-us) AppleWebKit/531.21.10 (KHTML, like Gecko) Mobile/7B405")  # noqa


def test_handles_null_user_agent():
    assert "unknown" == process_user_agent(None)
