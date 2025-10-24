from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.google_drive.naming import (  # noqa: E402
    drive_name_variants,
    drive_suffix_matches,
    looks_like_header_row,
    normalize_drive_text,
)
from app.services.excel_templates import FEATURE_LIST_EXPECTED_HEADERS  # noqa: E402


def test_normalize_drive_text_collapses_whitespace_and_case() -> None:
    assert normalize_drive_text("  Foo\u00a0Bar  ") == "foo bar"


def test_drive_name_variants_include_version_and_extensionless_forms() -> None:
    variants = drive_name_variants("기능리스트 v1.0.xlsx")
    assert "기능리스트 v1.0" in variants
    assert "기능리스트" in variants
    assert any(value.replace(" ", "") == "기능리스트v10" for value in variants)


def test_drive_suffix_matches_ignores_spacing_and_extension() -> None:
    assert drive_suffix_matches("기능 리스트 v1.0.xlsx", "기능리스트")
    assert drive_suffix_matches("테스트 케이스.xlsx", "테스트케이스.xlsx")
    assert not drive_suffix_matches("다른파일.xlsx", "기능리스트")


def test_looks_like_header_row_requires_threshold_matches() -> None:
    noisy_header = (" 대분류 (필수)", "중분류\n항목", "소분류-예시", "상세 설명")
    assert looks_like_header_row(noisy_header, FEATURE_LIST_EXPECTED_HEADERS)

    insufficient = ("대분류", "", "기타", "", "")
    assert not looks_like_header_row(insufficient, FEATURE_LIST_EXPECTED_HEADERS)

