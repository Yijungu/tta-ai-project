from __future__ import annotations

import importlib.util


def pytest_configure() -> None:
    try:
        from anyio._core import _eventloop
    except Exception:
        return

    if importlib.util.find_spec("trio") is not None:
        return

    backends = tuple(name for name in getattr(_eventloop, "BACKENDS", ()) if name != "trio")
    if backends:
        _eventloop.BACKENDS = backends  # type: ignore[attr-defined]

