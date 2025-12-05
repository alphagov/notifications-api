from dataclasses import dataclass

from sqlalchemy import event

from app import db


@dataclass
class QueryInfo:
    statement: str
    parameters: tuple | dict | None
    bind_key: str | None


class QueryRecorder:
    def __init__(self):
        self.queries: list[QueryInfo] = []
        self._listeners = []

    def __enter__(self):
        # Register listeners for all engines to capture bind_key
        for bind_key, engine in db.engines.items():
            listener = self._listener(bind_key)
            event.listen(engine, "before_cursor_execute", listener)
            self._listeners.append((engine, listener))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Remove all listeners
        for engine, listener in self._listeners:
            event.remove(engine, "before_cursor_execute", listener)
        self._listeners.clear()

    def _listener(self, bind_key):
        """Create a listener function that captures the bind_key in its closure."""

        def listener(conn, cursor, statement, parameters, context, executemany):
            self.queries.append(
                QueryInfo(
                    statement=statement,
                    parameters=parameters,
                    bind_key=bind_key,
                )
            )

        return listener
