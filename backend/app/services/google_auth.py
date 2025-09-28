from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
from fastapi import HTTPException

from ..core.settings import Settings
from ..token_store import StoredTokens, TokenStorage

logger = logging.getLogger(__name__)


def build_frontend_redirect(settings: Settings, status: str, message: Optional[str] = None) -> str:
    parsed = list(urlparse(settings.frontend_redirect_url))
    query: Dict[str, str] = dict(parse_qsl(parsed[4]))
    query["auth"] = status
    if message:
        query["message"] = message
    parsed[4] = urlencode(query, doseq=True)
    return urlunparse(parsed)


def load_tokens_for_drive(storage: TokenStorage, google_id: Optional[str]) -> StoredTokens:
    if google_id:
        stored = storage.load_by_google_id(google_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="요청한 Google 계정 토큰을 찾을 수 없습니다.")
        return stored

    accounts = storage.list_accounts()
    if not accounts:
        raise HTTPException(status_code=404, detail="저장된 Google 계정이 없습니다. 먼저 로그인하세요.")

    for account in accounts:
        stored = storage.load_by_google_id(account.google_id)
        if stored is not None:
            return stored

    raise HTTPException(status_code=404, detail="저장된 Google 계정 토큰을 찾을 수 없습니다.")


def _is_token_expired(tokens: StoredTokens) -> bool:
    if tokens.expires_in <= 0:
        return False

    expires_at = tokens.saved_at + timedelta(seconds=tokens.expires_in)
    now = datetime.now(timezone.utc)
    return now >= expires_at - timedelta(minutes=1)


async def refresh_access_token(settings: Settings, storage: TokenStorage, tokens: StoredTokens) -> StoredTokens:
    if not tokens.refresh_token:
        raise HTTPException(status_code=401, detail="Google 인증이 만료되었습니다. 다시 로그인해주세요.")

    data = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": tokens.refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post("https://oauth2.googleapis.com/token", data=data)

    if response.is_error:
        logger.error("Google token refresh failed: %s", response.text)
        raise HTTPException(status_code=502, detail="Google 토큰을 새로고침하지 못했습니다. 다시 로그인해주세요.")

    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        logger.error("Google token refresh response missing access_token: %s", payload)
        raise HTTPException(status_code=502, detail="Google 토큰을 새로고침하지 못했습니다. 다시 로그인해주세요.")

    merged_payload: Dict[str, object] = {
        "access_token": access_token,
        "refresh_token": payload.get("refresh_token") or tokens.refresh_token,
        "scope": payload.get("scope", tokens.scope),
        "token_type": payload.get("token_type", tokens.token_type),
        "expires_in": int(payload.get("expires_in", tokens.expires_in)),
    }

    return storage.save(
        google_id=tokens.google_id,
        display_name=tokens.display_name,
        email=tokens.email,
        payload=merged_payload,
    )


async def ensure_valid_tokens(settings: Settings, storage: TokenStorage, tokens: StoredTokens) -> StoredTokens:
    if _is_token_expired(tokens):
        return await refresh_access_token(settings, storage, tokens)
    return tokens
