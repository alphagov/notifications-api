from gunicorn_config import keepalive, timeout, worker_class, workers


def test_gunicorn_config():
    assert workers == 4
    assert worker_class == "gevent"
    assert keepalive == 0
    assert timeout == 30
