from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Mapping


PromptTemplate = Dict[str, str]


DEFAULT_PROMPTS: Dict[str, PromptTemplate] = {
    "feature-list": {
        "system": "당신은 소프트웨어 기획 QA 리드입니다. 업로드된 요구사항을 기반으로 기능 정의서를 작성합니다.",
        "instruction": (
            "요구사항 자료에서 주요 기능을 발췌하여 CSV로 정리하세요. "
            "다음 열을 포함해야 합니다: 대분류, 중분류, 소분류. "
            "각 열은 템플릿의 계층 구조에 맞춰 핵심 기능을 요약해야 합니다."
        ),
    },
    "testcase-generation": {
        "system": "당신은 소프트웨어 QA 테스터입니다. 업로드된 요구사항을 읽고 테스트 케이스 초안을 설계합니다.",
        "instruction": (
            "요구사항을 분석하여 테스트 케이스를 CSV로 작성하세요. "
            "다음 열을 포함합니다: 대분류, 중분류, 소분류, 테스트 케이스 ID, 테스트 시나리오, 입력(사전조건 포함), 기대 출력(사후조건 포함), 테스트 결과, 상세 테스트 결과, 비고. "
            "테스트 케이스 ID는 TC-001과 같이 순차적으로 부여하고, 테스트 결과는 기본값으로 '미실행'을 사용하세요."
        ),
    },
    "defect-report": {
        "system": "당신은 QA 분석가입니다. 업로드된 테스트 로그와 증적 자료를 바탕으로 결함 요약을 작성합니다.",
        "instruction": (
            "자료를 분석해 주요 결함을 요약한 CSV를 작성하세요. 열은 결함 ID, 심각도, 발생 모듈, 현상 요약, 제안 조치입니다. "
            "결함 ID는 BUG-001 형식을 사용하고, 심각도는 치명/중대/보통/경미 중 하나로 표기합니다."
        ),
    },
    "security-report": {
        "system": "당신은 보안 컨설턴트입니다. 업로드된 보안 점검 결과를 요약한 리포트를 만듭니다.",
        "instruction": (
            "자료를 바탕으로 취약점을 정리한 CSV를 작성하세요. 열은 취약점 ID, 위험도, 영향 영역, 발견 내용, 권장 조치입니다. "
            "위험도는 높음/중간/낮음 중 하나를 사용합니다."
        ),
    },
    "performance-report": {
        "system": "당신은 성능 엔지니어입니다. 업로드된 성능 측정 자료를 분석하여 결과를 요약합니다.",
        "instruction": (
            "자료를 분석하여 주요 시나리오의 성능을 정리한 CSV를 작성하세요. 열은 시나리오, 평균 응답(ms), 처리량(TPS), 자원 사용 요약, 개선 제안입니다."
        ),
    },
}


class PromptStore:
    """File-backed store for AI prompt templates."""

    def __init__(
        self,
        storage_path: Path,
        defaults: Mapping[str, PromptTemplate] | None = None,
    ) -> None:
        self._storage_path = storage_path
        self._defaults = dict(defaults or DEFAULT_PROMPTS)
        self._lock = threading.Lock()
        self._cache: Dict[str, PromptTemplate] | None = None

    def get_prompt(self, menu_id: str) -> PromptTemplate | None:
        """Return the prompt template for the given menu if it exists."""

        prompts = self._load()
        prompt = prompts.get(menu_id)
        if not prompt:
            return None
        return {"system": prompt.get("system", ""), "instruction": prompt.get("instruction", "")}

    def update_prompt(self, menu_id: str, prompt: PromptTemplate) -> PromptTemplate:
        """Persist and return the updated prompt template for the given menu."""

        normalized = {
            "system": str(prompt.get("system", "")).strip(),
            "instruction": str(prompt.get("instruction", "")).strip(),
        }

        with self._lock:
            prompts = self._load(locked=True)
            prompts[menu_id] = normalized
            self._save(prompts)
            return prompts[menu_id]

    def list_prompts(self) -> Dict[str, PromptTemplate]:
        """Return a copy of all stored prompt templates."""

        prompts = self._load()
        return {key: value.copy() for key, value in prompts.items()}

    def _load(self, locked: bool = False) -> Dict[str, PromptTemplate]:
        if self._cache is not None:
            return self._cache

        if not locked:
            with self._lock:
                return self._load(locked=True)

        if self._storage_path.exists():
            try:
                with self._storage_path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    parsed: Dict[str, PromptTemplate] = {}
                    for key, value in data.items():
                        if isinstance(value, dict):
                            parsed[key] = {
                                "system": str(value.get("system", "")),
                                "instruction": str(value.get("instruction", "")),
                            }
                    if parsed:
                        self._cache = parsed
                        return self._cache
            except Exception:
                # Ignore malformed files and fall back to defaults.
                pass

        prompts = {key: value.copy() for key, value in self._defaults.items()}
        self._cache = prompts
        self._ensure_parent_exists()
        self._save(prompts)
        return prompts

    def _save(self, prompts: Dict[str, PromptTemplate]) -> None:
        self._ensure_parent_exists()
        with self._storage_path.open("w", encoding="utf-8") as file:
            json.dump(prompts, file, ensure_ascii=False, indent=2)
        self._cache = prompts.copy()

    def _ensure_parent_exists(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
