from app import StatsdClient


def test_calls_inc_with_correct_params(notify_api, mocker):
    mocker.patch('app.clients.email')
    stats_client = StatsdClient(notify_api.current_app)
    assert 1 == 2

