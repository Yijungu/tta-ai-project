from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

pytest.importorskip("openpyxl")
from openpyxl import Workbook  # type: ignore

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.google_drive.feature_lists import (  # noqa: E402
    build_feature_list_csv,
    parse_feature_list_workbook,
    populate_workbook,
)


def _build_feature_list_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "기능리스트"
    sheet.append(["대분류", "중분류", "소분류", "기능 설명"])
    sheet.append(["보안", "인증", "로그인", "사용자 로그인 처리"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_feature_list_workbook_extracts_rows() -> None:
    context, rows = parse_feature_list_workbook(_build_feature_list_workbook())
    assert context["sheetName"] == "기능리스트"
    assert context["startRow"] >= 2
    assert rows == [
        {
            "majorCategory": "보안",
            "middleCategory": "인증",
            "minorCategory": "로그인",
            "featureDescription": "사용자 로그인 처리",
        }
    ]


def test_build_feature_list_csv_generates_expected_header() -> None:
    csv_text = build_feature_list_csv(
        [
            {
                "majorCategory": "보안",
                "middleCategory": "인증",
                "minorCategory": "로그인",
                "featureDescription": "사용자 로그인 처리",
            }
        ]
    )
    assert "대분류" in csv_text.splitlines()[0]
    assert "사용자 로그인 처리" in csv_text


def test_populate_workbook_accepts_optional_overview() -> None:
    csv_text = build_feature_list_csv(
        [
            {
                "majorCategory": "보안",
                "middleCategory": "인증",
                "minorCategory": "로그인",
                "featureDescription": "사용자 로그인 처리",
            }
        ]
    )
    updated = populate_workbook(_build_feature_list_workbook(), csv_text, "요약")
    assert isinstance(updated, bytes) and len(updated) > 0

