"""Repository-wide Python runtime customizations."""

from __future__ import annotations

import importlib.util


def _ensure_anyio_backends() -> None:
    try:
        from anyio._core import _eventloop
    except Exception:
        return

    has_trio = importlib.util.find_spec("trio") is not None
    if has_trio:
        return

    backends = tuple(name for name in getattr(_eventloop, "BACKENDS", ()) if name != "trio")
    if backends:
        _eventloop.BACKENDS = backends  # type: ignore[attr-defined]


_ensure_anyio_backends()

