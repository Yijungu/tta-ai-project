from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.google_drive import defect_reports, security_reports  # noqa: E402


def test_defect_reports_delegate_to_excel_population(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, bytes | str] = {}

    def fake_populate(workbook_bytes: bytes, csv_text: str) -> bytes:
        captured["workbook"] = workbook_bytes
        captured["csv"] = csv_text
        return b"updated"

    monkeypatch.setattr(defect_reports, "_populate_defect_report", fake_populate)
    result = defect_reports.populate_workbook(b"source", "csv")
    assert result == b"updated"
    assert captured == {"workbook": b"source", "csv": "csv"}


def test_security_reports_delegate_to_excel_population(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, bytes | str] = {}

    def fake_populate(workbook_bytes: bytes, csv_text: str) -> bytes:
        captured["workbook"] = workbook_bytes
        captured["csv"] = csv_text
        return b"updated"

    monkeypatch.setattr(security_reports, "_populate_security_report", fake_populate)
    result = security_reports.populate_workbook(b"source", "csv")
    assert result == b"updated"
    assert captured == {"workbook": b"source", "csv": "csv"}

