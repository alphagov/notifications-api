from gunicorn_config import keepalive, timeout, worker_class, workers


def test_gunicorn_config():
    assert workers == 4
    assert worker_class == "eventlet"
    assert keepalive == 90
    assert timeout == 30
