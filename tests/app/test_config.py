from celery.schedules import crontab
from sqlalchemy import text

from app import db
from app.config import QueueNames


def test_queue_names_all_queues_correct():
    # Need to ensure that all_queues() only returns queue names used in API
    queues = QueueNames.all_queues()
    assert len(queues) == 18
    assert {
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
        QueueNames.LETTER_CALLBACKS,
        QueueNames.REPORT_REQUESTS_NOTIFICATIONS,
    } == set(queues)


def test_predefined_queues():
    prefix = "test-prefix-"
    aws_region = "eu-west-1"
    aws_account_id = "123456789012"

    class_queues = [
        value for key, value in vars(QueueNames).items() if not key.startswith("_") and isinstance(value, str)
    ]
    predefined_queues = QueueNames.predefined_queues(prefix, aws_region, aws_account_id)

    assert len(predefined_queues) == len(class_queues)

    for queue_name in class_queues:
        full_queue_name = f"{prefix}{queue_name}"
        assert full_queue_name in predefined_queues
        assert (
            predefined_queues[full_queue_name]["url"]
            == f"https://sqs.{aws_region}.amazonaws.com/{aws_account_id}/{full_queue_name}"
        )


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
    timeout = notify_db_session.execute(text("show statement_timeout")).scalar()
    assert timeout == "20min"
    assert notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["connect_args"]["options"] == "-c statement_timeout=1200000"

    assert db.engine.pool.size() == notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_size"]
    assert db.engine.pool.timeout() == notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_timeout"]
    assert db.engine.pool._recycle == notify_api.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_recycle"]
