from collections.abc import Callable, Iterable, Mapping
import psycopg2
import struct
import time
from contextlib import contextmanager
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from flask import current_app
from sqlalchemy import engine_from_config, pool, text
import sqlalchemy

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
import app.models

config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

config.set_main_option("sqlalchemy.url", current_app.config.get("SQLALCHEMY_DATABASE_URI"))
target_metadata = app.models.db.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """
    Exclude views from Alembic's consideration.
    """

    return object.info.get("managed_by_alembic", True)


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        compare_type=True,
        include_object=include_object,
        target_metadata=target_metadata,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    engine = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    connection = engine.connect()
    try:
        context.configure(
            connection=connection,
            compare_type=True,
            include_object=include_object,
            target_metadata=target_metadata,
            transaction_per_migration=True,
        )

        # take a *session-level* advisory lock to prevent multiple migration
        # processes attempting to run concurrently. being a session-level lock,
        # it should safely cover our few migrations that need to perform multiple
        # transactions.
        # advisory lock ids are 64b (signed) integers, so use the null-padded,
        # big-endian representation of the string "alembic"
        lock_id = struct.unpack(">q", struct.pack("8s", b"alembic"))[0]
        connection.execute(text("SELECT pg_advisory_lock(:id)"), {"id": lock_id})

        # abort any migrations if a lock (other than the above advisory lock)
        # cannot be acquired after one second.
        #
        # if we see issues with this lock timeout failing, we should try running
        # again when there are no locks on that table, perhaps at a quieter time.
        connection.execute(text("SET lock_timeout = 1000"))

        with context.begin_transaction():
            context.run_migrations()

        # if we're running on the main db (as opposed to the test db)
        if engine.url.database == "notification_api":
            with open(Path(__file__).parent / ".current-alembic-head", "w") as f:
                # write the current head to `.current-alembic-head`. This will prevent conflicting migrations
                # being merged at the same time and breaking the build.
                head = context.get_head_revision()
                f.write(head + "\n")
    finally:
        connection.close()


def retry_on_lock_error(
    *,
    func: Callable,
    args: Iterable = [],
    kwargs: Mapping = {},
    max_retries: int = 1,
    delay_secs: int = 0,
):
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except sqlalchemy.exc.OperationalError as e:
            # on the last attempt raise so we get a full stack trace
            if i + 1 == max_retries:
                raise

            if not isinstance(e.orig, psycopg2.errors.LockNotAvailable):
                raise

            print("Retrying due to LockNotAvailable error")
            print(e)
            time.sleep(delay_secs)


if context.is_offline_mode():
    run_migrations_offline()
else:
    retry_on_lock_error(func=run_migrations_online, max_retries=10, delay_secs=10)
