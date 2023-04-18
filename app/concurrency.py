from typing import Any, Callable, Sequence

import eventlet


def run_concurrently(*partials: Callable) -> Sequence[Any]:
    pool = eventlet.GreenPool(size=len(partials))

    results = [pool.spawn(partial) for partial in partials]

    pool.waitall()

    return tuple(result.wait() for result in results)
