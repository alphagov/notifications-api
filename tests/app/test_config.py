import importlib
import os
from unittest import mock

import pytest
from celery.schedules import crontab

from app import config, db
from app.config import QueueNames


def cf_conf():
    os.environ["ADMIN_BASE_URL"] = "cf"


@pytest.fixture
def reload_config():
    """
    Reset config, by simply re-running config.py from a fresh environment
    """
    old_env = os.environ.copy()

    yield

    os.environ.clear()
    for k, v in old_env.items():
        os.environ[k] = v

    importlib.reload(config)


def test_load_cloudfoundry_config_if_available(reload_config):
    os.environ["ADMIN_BASE_URL"] = "env"
    os.environ["VCAP_SERVICES"] = "some json blob"
    os.environ["VCAP_APPLICATION"] = "some json blob"

    with mock.patch("app.cloudfoundry_config.extract_cloudfoundry_config", side_effect=cf_conf) as cf_config:
        # reload config so that its module level code (ie: all of it) is re-instantiated
        importlib.reload(config)

    assert cf_config.called

    assert os.environ["ADMIN_BASE_URL"] == "cf"
    assert config.Config.ADMIN_BASE_URL == "cf"


def test_load_config_if_cloudfoundry_not_available(reload_config):
    os.environ["ADMIN_BASE_URL"] = "env"
    os.environ.pop("VCAP_SERVICES", None)

    with mock.patch("app.cloudfoundry_config.extract_cloudfoundry_config") as cf_config:
        # reload config so that its module level code (ie: all of it) is re-instantiated
        importlib.reload(config)

    assert not cf_config.called

    assert os.environ["ADMIN_BASE_URL"] == "env"
    assert config.Config.ADMIN_BASE_URL == "env"


def test_queue_names_all_queues_correct():
    # Need to ensure that all_queues() only returns queue names used in API
    queues = QueueNames.all_queues()
    assert len(queues) == 19
    assert set(
        [
            QueueNames.PERIODIC,
            QueueNames.DATABASE,
            QueueNames.SEND_SMS,
            QueueNames.SEND_EMAIL,
            QueueNames.SEND_LETTER,
            QueueNames.RESEARCH_MODE,
            QueueNames.REPORTING,
            QueueNames.JOBS,
            QueueNames.RETRY,
            QueueNames.NOTIFY,
            QueueNames.CREATE_LETTERS_PDF,
            QueueNames.CALLBACKS,
            QueueNames.CALLBACKS_RETRY,
            QueueNames.LETTERS,
            QueueNames.SES_CALLBACKS,
            QueueNames.SMS_CALLBACKS,
            QueueNames.SAVE_API_EMAIL,
            QueueNames.SAVE_API_SMS,
            QueueNames.BROADCASTS,
        ]
    ) == set(queues)


def test_no_celery_beat_tasks_scheduled_over_midnight_between_timezones(notify_api):
    badly_scheduled_tasks = []

    for task_name, task_info in notify_api.config["CELERY"]["beat_schedule"].items():
        schedule = task_info["schedule"]
        if not isinstance(schedule, crontab):
            continue

        # If a task is scheduled with hour='*' or hour='1-12', then `schedule.hour` is a set containing all of the
        # relevant integer values. So if we remove `23` and are left with an empty set, we know that this task could
        # only possibly run between 11pm and midnight UTC.
        if not (schedule.hour - {23}):
            badly_scheduled_tasks.append(task_name)

    assert not badly_scheduled_tasks, (
        "These tasks are only scheduled to run between 11:00pm and midnight UTC. "
        "Anything that runs between 11pm and midnight UTC will run on the same day when Europe/London is GMT, "
        "and the next day when Europe/London is BST. This could cause processing errors."
    )


def test_sqlalchemy_config(notify_api, notify_db_session):
    timeout = notify_db_session.execute("show statement_timeout").scalar()
    assert timeout == "20min"
    assert notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["options"] == "-c statement_timeout=1200000"

    assert db.engine.pool.size() == notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_size"]
    assert db.engine.pool.timeout() == notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_timeout"]
    assert db.engine.pool._recycle == notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_recycle"]
