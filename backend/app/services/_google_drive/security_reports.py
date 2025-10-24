"""Helpers for Drive security report workflows."""

from __future__ import annotations

from ..excel_templates import populate_security_report as _populate_security_report


def populate_workbook(workbook_bytes: bytes, csv_text: str) -> bytes:
    return _populate_security_report(workbook_bytes, csv_text)


def describe_imported_rows(row_count: int) -> str:
    return (
        f"총 {row_count}건의 보안 결함 리포트를 업데이트했습니다."
        if row_count
        else "보안 결함 리포트에 추가할 항목이 없습니다."
    )

