from __future__ import annotations

from flask import g, has_request_context


def init_request_timings() -> None:
    if not has_request_context():
        return
    if not hasattr(g, "request_timings"):
        g.request_timings = {}
    if not hasattr(g, "request_timing_context"):
        g.request_timing_context = {}


def record_timing(name: str, duration_seconds: float) -> None:
    if not has_request_context():
        return
    init_request_timings()
    g.request_timings[name] = round(duration_seconds * 1000.0, 3)


def add_context(**kwargs: object) -> None:
    if not has_request_context():
        return
    init_request_timings()
    g.request_timing_context.update({k: v for k, v in kwargs.items() if v is not None})


def get_timings() -> tuple[dict[str, float], dict[str, object]]:
    if not has_request_context():
        return {}, {}
    timings = getattr(g, "request_timings", {})
    context = getattr(g, "request_timing_context", {})
    return timings, context
