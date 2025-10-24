from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.services.google_drive.client import GoogleDriveClient  # noqa: E402
from app.token_store import StoredTokens  # noqa: E402


class DummyTokenStorage:
    def __init__(self, tokens: Dict[str, StoredTokens]) -> None:
        self.tokens = tokens
        self.saved_payload: Optional[Dict[str, Any]] = None

    def load_by_google_id(self, google_id: str) -> Optional[StoredTokens]:
        return self.tokens.get(google_id)

    def list_accounts(self) -> list[Any]:
        return [SimpleNamespace(google_id=gid) for gid in self.tokens]

    def save(
        self,
        *,
        google_id: str,
        display_name: str,
        email: Optional[str],
        payload: Dict[str, Any],
    ) -> StoredTokens:
        saved = StoredTokens(
            google_id=google_id,
            display_name=display_name,
            email=email,
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            scope=payload.get("scope", ""),
            token_type=payload.get("token_type", "Bearer"),
            expires_in=int(payload.get("expires_in", 0)),
            saved_at=datetime.now(timezone.utc),
        )
        self.tokens[google_id] = saved
        self.saved_payload = payload
        return saved


class DummyOAuth:
    def __init__(self) -> None:
        self.called = False

    def ensure_credentials(self) -> None:
        self.called = True


def _build_tokens(expires_in: int, offset_seconds: int = 0) -> StoredTokens:
    return StoredTokens(
        google_id="tester",
        display_name="Tester",
        email="tester@example.com",
        access_token="initial",
        refresh_token="refresh",
        scope="scope",
        token_type="Bearer",
        expires_in=expires_in,
        saved_at=datetime.now(timezone.utc) - timedelta(seconds=offset_seconds),
    )


def test_ensure_valid_tokens_refreshes_when_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _build_tokens(expires_in=10, offset_seconds=4000)
    storage = DummyTokenStorage({stored.google_id: stored})
    client = GoogleDriveClient(
        Settings(
            client_id="id",
            client_secret="secret",
            redirect_uri="",
            frontend_redirect_url="http://example.com",
            tokens_path=Path("/tmp/test.db"),
            openai_api_key="",
            openai_model="gpt",
        ),
        storage,
        DummyOAuth(),
    )

    refreshed = _build_tokens(expires_in=3600)

    async def fake_refresh(tokens: StoredTokens) -> StoredTokens:
        assert tokens is stored
        return refreshed

    monkeypatch.setattr(client, "refresh_access_token", fake_refresh)

    result = asyncio.run(client.ensure_valid_tokens(stored))
    assert result is refreshed


def test_load_tokens_defaults_to_first_account() -> None:
    stored = _build_tokens(expires_in=3600)
    storage = DummyTokenStorage({stored.google_id: stored})
    client = GoogleDriveClient(
        Settings(
            client_id="id",
            client_secret="secret",
            redirect_uri="",
            frontend_redirect_url="http://example.com",
            tokens_path=Path("/tmp/test.db"),
            openai_api_key="",
            openai_model="gpt",
        ),
        storage,
        DummyOAuth(),
    )

    assert client.load_tokens(None) is stored

