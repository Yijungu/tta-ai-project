"""Helpers for Drive defect report workflows."""

from __future__ import annotations

from ..excel_templates import populate_defect_report as _populate_defect_report


def populate_workbook(workbook_bytes: bytes, csv_text: str) -> bytes:
    return _populate_defect_report(workbook_bytes, csv_text)


def describe_imported_rows(row_count: int) -> str:
    return f"총 {row_count}건의 결함 보고서를 업데이트했습니다." if row_count else "결함 보고서에 추가할 항목이 없습니다."

