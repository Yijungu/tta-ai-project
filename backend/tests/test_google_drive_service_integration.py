from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Sequence, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.services.google_drive.client import XLSX_MIME_TYPE  # noqa: E402
from app.services.google_drive.service import GoogleDriveService  # noqa: E402
from app.token_store import StoredTokens  # noqa: E402


def _build_tokens() -> StoredTokens:
    return StoredTokens(
        google_id="tester",
        display_name="Tester",
        email="tester@example.com",
        access_token="token",
        refresh_token="refresh",
        scope="scope",
        token_type="Bearer",
        expires_in=3600,
        saved_at=datetime.now(timezone.utc),
    )


class FakeClient:
    def __init__(self, tokens: StoredTokens) -> None:
        self.oauth_service = SimpleNamespace(ensure_credentials=lambda: None)
        self._tokens = tokens
        self.upload_called = False

    def load_tokens(self, google_id: Optional[str]) -> StoredTokens:
        assert google_id in (None, self._tokens.google_id)
        return self._tokens

    async def ensure_valid_tokens(self, tokens: StoredTokens) -> StoredTokens:
        return tokens

    async def find_root_folder(
        self, tokens: StoredTokens, *, folder_name: str
    ) -> Tuple[Optional[Dict[str, Any]], StoredTokens]:
        return ({"id": "root", "name": folder_name}, tokens)

    async def create_root_folder(
        self, tokens: StoredTokens, *, folder_name: str
    ) -> Tuple[Dict[str, Any], StoredTokens]:
        return {"id": "root", "name": folder_name}, tokens

    async def list_child_folders(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
    ) -> Tuple[Sequence[Dict[str, Any]], StoredTokens]:
        if parent_id == "root":
            return ([{"id": "project", "name": "샘플 프로젝트"}], tokens)
        return ([], tokens)

    async def list_child_files(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        mime_type: Optional[str] = None,
    ) -> Tuple[Sequence[Dict[str, Any]], StoredTokens]:
        assert parent_id == "root"
        return (
            [
                {
                    "id": "criteria",
                    "name": "보안성 결함판단기준표 v1.0.xlsx",
                    "mimeType": XLSX_MIME_TYPE,
                }
            ],
            tokens,
        )

    async def upload_file(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - guard
        self.upload_called = True
        return {}, self._tokens


def test_ensure_drive_setup_returns_existing_criteria() -> None:
    tokens = _build_tokens()
    service = GoogleDriveService(
        Settings(
            client_id="id",
            client_secret="secret",
            redirect_uri="",
            frontend_redirect_url="http://example.com",
            tokens_path=Path("/tmp/test.db"),
            openai_api_key="",
            openai_model="gpt",
        ),
        SimpleNamespace(),
        SimpleNamespace(ensure_credentials=lambda: None),
    )
    fake_client = FakeClient(tokens)
    service._client = fake_client  # type: ignore[attr-defined]

    result = asyncio.run(service.ensure_drive_setup(tokens.google_id))

    assert result["folderId"] == "root"
    assert result["criteria"]["fileId"] == "criteria"
    assert result["projects"] == [{"id": "project", "name": "샘플 프로젝트", "createdTime": None, "modifiedTime": None}]
    assert not fake_client.upload_called

