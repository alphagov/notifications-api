import logging
import os
import signal
from logging.config import dictConfig as logging_dictConfig
from sys import exit
from time import sleep
from typing import Final

from notifications_utils.semconv import set_service_instance_id
from opentelemetry.instrumentation import auto_instrumentation

from app import create_app
from app.dao.notifications_wal_changes_dao import (
    REPLICATION_SLOT_UPTO_NCHANGES,
    LockNotAcquired,
    dao_process_notifications_replication_slot_changes,
)
from app.notify_api_flask_app import NotifyApiFlaskApp

terminating_signals = frozenset((signal.SIGINT, signal.SIGTERM))


logger = logging.getLogger("db_streamer")


TOPLEVEL_EXCEPTION_LIMIT: Final[int] = 20
toplevel_exception_count: int = 0


def db_streamer_loop(app) -> None:
    global toplevel_exception_count

    while (pending := signal.sigpending()).isdisjoint(terminating_signals):
        try:
            with app.app_context():
                try:
                    result = dao_process_notifications_replication_slot_changes(
                        upto_nchanges=REPLICATION_SLOT_UPTO_NCHANGES,
                    )
                except LockNotAcquired:
                    # back off, we'd prefer whatever else has the lock to be able to immediately
                    # re-acquire it and perform another iteration if it wants to
                    sleep(1)
                    continue

                if result.raw_change_rows < REPLICATION_SLOT_UPTO_NCHANGES:
                    # we exhausted the changes, loosen the loop
                    sleep(1)
        except Exception as e:
            toplevel_exception_count += 1
            if toplevel_exception_count >= TOPLEVEL_EXCEPTION_LIMIT:
                logger.exception(
                    "Exiting due to exception %s (TOPLEVEL_EXCEPTION_LIMIT reached)",
                    e,
                    extra={"toplevel_exception_count": toplevel_exception_count},
                )
                exit(49)  # arbitrary number unlikely to collide with anything else
            else:
                logger.exception(
                    "Caught exception %s", repr(e), extra={"toplevel_exception_count": toplevel_exception_count}
                )
                sleep(1)
    else:
        logger.warning("Received terminating signal(s): %s", ", ".join(s.name for s in (pending & terminating_signals)))


if __name__ == "__main__":
    # block these signals - instead we will periodically check for them with sigpending().
    # this must be set up *before* we do anything that will spawn a background thread (e.g. otel)
    signal.pthread_sigmask(signal.SIG_BLOCK, terminating_signals)

    if os.environ.get("OTEL_SERVICE_NAME") is not None:
        set_service_instance_id()
        auto_instrumentation.initialize()

    application = NotifyApiFlaskApp("app")
    create_app(application)
    application.config["ENABLE_DATABASE_CONNECTION_CHECKOUT_OUTSIDE_CONTEXT_WARNING"] = False

    logging_dictConfig(
        {
            # configuration very similar to that we apply to celery
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "generic": {
                    "class": "notifications_utils.logging.formatting.JSONFormatter",
                    "format": "ext://notifications_utils.logging.formatting.LOG_FORMAT",
                    "datefmt": "ext://notifications_utils.logging.formatting.TIME_FORMAT",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "generic",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "db_streamer": {"handlers": ["default"], "level": "INFO", "propagate": False},
            },
        }
    )
    logger.info("Logging configured")

    db_streamer_loop(application)
