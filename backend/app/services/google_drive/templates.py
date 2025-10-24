"""Google Drive template utilities and constants."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, TypedDict

from fastapi import HTTPException

try:  # pragma: no cover - optional dependency guard
    from openpyxl import Workbook
except ImportError:  # pragma: no cover
    Workbook = None  # type: ignore

from ...token_store import StoredTokens
from ..excel_templates import FEATURE_LIST_EXPECTED_HEADERS, populate_testcase_list
from .defect_reports import populate_workbook as populate_defect_report_workbook
from .security_reports import populate_workbook as populate_security_report_workbook


TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "template"

PLACEHOLDER_PATTERNS: Tuple[str, ...] = (
    "GS-B-XX-XXXX",
    "GS-B-2X-XXXX",
    "GS-X-X-XXXX",
)

SHARED_CRITERIA_FILE_CANDIDATES: Tuple[str, ...] = (
    "보안성 결함판단기준표 v1.0.xlsx",
    "결함판단기준표 v1.0.xlsx",
    "결함 판단 기준표 v1.0.xlsx",
    "결함 판단기준표 v1.0.xlsx",
    "공유 결함판단기준표 v1.0.xlsx",
    "공유 결함 판단 기준표 v1.0.xlsx",
)


def normalize_shared_criteria_name(name: str) -> str:
    base = name.strip().lower()
    if base.endswith(".xlsx"):
        base = base[:-5]
    return "".join(base.split())


SHARED_CRITERIA_NORMALIZED_NAMES = {
    normalize_shared_criteria_name(candidate) for candidate in SHARED_CRITERIA_FILE_CANDIDATES
}
PREFERRED_SHARED_CRITERIA_FILE_NAME = SHARED_CRITERIA_FILE_CANDIDATES[0]


def is_shared_criteria_candidate(filename: str) -> bool:
    try:
        normalized = normalize_shared_criteria_name(filename)
    except Exception:
        return False
    return normalized in SHARED_CRITERIA_NORMALIZED_NAMES


def build_default_shared_criteria_workbook() -> bytes:
    if Workbook is None:  # pragma: no cover - optional dependency guard
        raise HTTPException(status_code=500, detail="openpyxl 패키지가 필요합니다.")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "결함판단기준"
    headers = [
        "Invicti 결과",
        "결함 요약",
        "결함정도",
        "발생빈도",
        "품질특성",
        "결함 설명",
        "결함 제외 여부",
    ]
    sheet.append(headers)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def load_shared_criteria_template_bytes() -> bytes:
    for candidate in SHARED_CRITERIA_FILE_CANDIDATES:
        template_path = TEMPLATE_ROOT / candidate
        if template_path.exists():
            return template_path.read_bytes()
    return build_default_shared_criteria_workbook()


class SpreadsheetRule(TypedDict):
    folder_name: str
    file_suffix: str
    populate: Any


def _populate_feature_list(*args: Any, **kwargs: Any) -> bytes:
    from .feature_lists import populate_workbook

    return populate_workbook(*args, **kwargs)


SPREADSHEET_RULES: Dict[str, SpreadsheetRule] = {
    "feature-list": {
        "folder_name": "가.계획",
        "file_suffix": "기능리스트 v1.0.xlsx",
        "populate": _populate_feature_list,
    },
    "testcase-generation": {
        "folder_name": "나.설계",
        "file_suffix": "테스트케이스.xlsx",
        "populate": populate_testcase_list,
    },
    "defect-report": {
        "folder_name": "다.수행",
        "file_suffix": "결함리포트 v1.0.xlsx",
        "populate": populate_defect_report_workbook,
    },
    "security-report": {
        "folder_name": "다.수행",
        "file_suffix": "결함리포트 v1.0.xlsx",
        "populate": populate_security_report_workbook,
    },
}


@dataclass
class ResolvedSpreadsheet:
    rule: SpreadsheetRule
    tokens: StoredTokens
    folder_id: str
    file_id: str
    file_name: str
    mime_type: Optional[str]
    modified_time: Optional[str]
    content: Optional[bytes] = None


FEATURE_LIST_START_ROW = 8
FEATURE_LIST_SHEET_CANDIDATES: Tuple[str, ...] = (
    "기능리스트",
    "기능 리스트",
    "feature list",
)


def iter_template_files(template_root: Path) -> Sequence[Path]:
    if not template_root.exists():
        raise HTTPException(status_code=500, detail="template 폴더를 찾을 수 없습니다.")

    collected: list[Path] = []
    for root_dir, _dirnames, filenames in os.walk(template_root):
        current_path = Path(root_dir)
        for filename in sorted(filenames):
            collected.append(current_path / filename)
    return collected

