"""Compatibility shim for Google Drive service helpers.

This module preserves the historical ``app.services.google_drive`` import
location while delegating implementation details to the reorganized helper
package that now lives under ``app.services._google_drive``.  Keeping the shim in
place means downstream callers continue to ``import app.services.google_drive``
without running into Git tree conflicts (file vs. directory) when merging.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Final

# Point Python's module loader at the directory that hosts the implementation
# modules.  With ``__path__`` set, the interpreter will happily resolve dotted
# imports such as ``app.services.google_drive.client`` or ``...templates`` even
# though the actual code lives in ``_google_drive``.
_IMPLEMENTATION_PATH: Final[str] = Path(__file__).with_name("_google_drive").as_posix()
__path__ = [_IMPLEMENTATION_PATH]

# Re-export the primary service so existing imports keep working.
GoogleDriveService = importlib.import_module("._google_drive.service", __package__).GoogleDriveService

__all__ = ["GoogleDriveService"]
