"""HTTP client for interacting with Google Drive APIs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Sequence, Tuple

import httpx
from fastapi import HTTPException

from ...config import Settings
from ...token_store import StoredTokens, TokenStorage
from ..oauth import GOOGLE_TOKEN_ENDPOINT, GoogleOAuthService

logger = logging.getLogger(__name__)


DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_FILES_ENDPOINT = "/files"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_SHEETS_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class GoogleDriveClient:
    def __init__(
        self,
        settings: Settings,
        token_storage: TokenStorage,
        oauth_service: GoogleOAuthService,
    ) -> None:
        self._settings = settings
        self._token_storage = token_storage
        self._oauth_service = oauth_service

    @property
    def oauth_service(self) -> GoogleOAuthService:
        return self._oauth_service

    def load_tokens(self, google_id: Optional[str]) -> StoredTokens:
        if google_id:
            stored = self._token_storage.load_by_google_id(google_id)
            if stored is None:
                raise HTTPException(status_code=404, detail="요청한 Google 계정 토큰을 찾을 수 없습니다.")
            return stored

        accounts = self._token_storage.list_accounts()
        if not accounts:
            raise HTTPException(status_code=404, detail="저장된 Google 계정이 없습니다. 먼저 로그인하세요.")

        for account in accounts:
            stored = self._token_storage.load_by_google_id(account.google_id)
            if stored is not None:
                return stored

        raise HTTPException(status_code=404, detail="저장된 Google 계정 토큰을 찾을 수 없습니다.")

    def _is_token_expired(self, tokens: StoredTokens) -> bool:
        if tokens.expires_in <= 0:
            return False

        expires_at = tokens.saved_at + timedelta(seconds=tokens.expires_in)
        now = datetime.now(timezone.utc)
        return now >= expires_at - timedelta(minutes=1)

    async def refresh_access_token(self, tokens: StoredTokens) -> StoredTokens:
        if not tokens.refresh_token:
            raise HTTPException(status_code=401, detail="Google 인증이 만료되었습니다. 다시 로그인해주세요.")

        data = {
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "refresh_token": tokens.refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(GOOGLE_TOKEN_ENDPOINT, data=data)

        if response.is_error:
            logger.error("Google token refresh failed: %s", response.text)
            raise HTTPException(status_code=502, detail="Google 토큰을 새로고침하지 못했습니다. 다시 로그인해주세요.")

        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            logger.error("Google token refresh response missing access_token: %s", payload)
            raise HTTPException(status_code=502, detail="Google 토큰을 새로고침하지 못했습니다. 다시 로그인해주세요.")

        merged_payload: Dict[str, Any] = {
            "access_token": access_token,
            "refresh_token": payload.get("refresh_token") or tokens.refresh_token,
            "scope": payload.get("scope", tokens.scope),
            "token_type": payload.get("token_type", tokens.token_type),
            "expires_in": int(payload.get("expires_in", tokens.expires_in)),
        }

        return self._token_storage.save(
            google_id=tokens.google_id,
            display_name=tokens.display_name,
            email=tokens.email,
            payload=merged_payload,
        )

    async def ensure_valid_tokens(self, tokens: StoredTokens) -> StoredTokens:
        if self._is_token_expired(tokens):
            return await self.refresh_access_token(tokens)
        return tokens

    async def request(
        self,
        tokens: StoredTokens,
        *,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        base_url: str = DRIVE_API_BASE,
    ) -> Tuple[Dict[str, Any], StoredTokens]:
        current_tokens = tokens

        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {current_tokens.access_token}",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(timeout=10.0, base_url=base_url) as client:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )

            if response.status_code != 401:
                if response.is_error:
                    logger.error("Google Drive API %s %s failed: %s", method, path, response.text)
                    raise HTTPException(
                        status_code=502,
                        detail="Google Drive API 요청이 실패했습니다. 잠시 후 다시 시도해주세요.",
                    )

                data = response.json() if response.text else {}
                return data, current_tokens

            if attempt == 0:
                current_tokens = await self.refresh_access_token(current_tokens)
                continue

        raise HTTPException(status_code=401, detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.")

    async def find_root_folder(
        self, tokens: StoredTokens, *, folder_name: str
    ) -> Tuple[Optional[Dict[str, Any]], StoredTokens]:
        escaped_name = folder_name.replace("'", "\\'")
        query = (
            f"name = '{escaped_name}' and "
            f"mimeType = '{DRIVE_FOLDER_MIME_TYPE}' and "
            "'root' in parents and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id,name)",
            "pageSize": 1,
            "spaces": "drive",
        }

        data, updated_tokens = await self.request(
            tokens,
            method="GET",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
        )

        files = data.get("files")
        if isinstance(files, Sequence) and files:
            first = files[0]
            if isinstance(first, dict):
                return first, updated_tokens

        return None, updated_tokens

    async def create_root_folder(
        self, tokens: StoredTokens, *, folder_name: str
    ) -> Tuple[Dict[str, Any], StoredTokens]:
        body = {
            "name": folder_name,
            "mimeType": DRIVE_FOLDER_MIME_TYPE,
            "parents": ["root"],
        }
        params = {"fields": "id,name"}

        data, updated_tokens = await self.request(
            tokens,
            method="POST",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
            json_body=body,
        )

        if not isinstance(data, dict) or "id" not in data:
            logger.error("Google Drive create folder response missing id: %s", data)
            raise HTTPException(status_code=502, detail="Google Drive 폴더를 생성하지 못했습니다. 다시 시도해주세요.")

        return data, updated_tokens

    async def create_child_folder(
        self, tokens: StoredTokens, *, name: str, parent_id: str
    ) -> Tuple[Dict[str, Any], StoredTokens]:
        body = {
            "name": name,
            "mimeType": DRIVE_FOLDER_MIME_TYPE,
            "parents": [parent_id],
        }
        params = {"fields": "id,name,parents"}

        data, updated_tokens = await self.request(
            tokens,
            method="POST",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
            json_body=body,
        )

        if not isinstance(data, dict) or "id" not in data:
            logger.error("Google Drive create child folder response missing id: %s", data)
            raise HTTPException(status_code=502, detail="Google Drive 하위 폴더를 생성하지 못했습니다. 다시 시도해주세요.")

        return data, updated_tokens

    async def upload_file(
        self,
        tokens: StoredTokens,
        *,
        file_name: str,
        parent_id: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], StoredTokens]:
        active_tokens = tokens

        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {active_tokens.access_token}",
            }
            metadata = {"name": file_name, "parents": [parent_id]}
            files = {
                "metadata": (
                    "metadata",
                    json.dumps(metadata),
                    "application/json; charset=UTF-8",
                ),
                "file": (
                    file_name,
                    content,
                    content_type or "application/pdf",
                ),
            }

            async with httpx.AsyncClient(timeout=30.0, base_url=DRIVE_UPLOAD_BASE) as client:
                response = await client.post(
                    f"{DRIVE_FILES_ENDPOINT}?uploadType=multipart&fields=id,name,parents",
                    headers=headers,
                    files=files,
                )

            if response.status_code == 401 and attempt == 0:
                active_tokens = await self.refresh_access_token(active_tokens)
                continue

            if response.is_error:
                logger.error("Google Drive file upload failed for %s: %s", file_name, response.text)
                raise HTTPException(
                    status_code=502,
                    detail="파일을 Google Drive에 업로드하지 못했습니다. 잠시 후 다시 시도해주세요.",
                )

            data = response.json()
            if not isinstance(data, dict) or "id" not in data:
                logger.error("Google Drive file upload response missing id: %s", data)
                raise HTTPException(status_code=502, detail="업로드한 파일의 ID를 확인하지 못했습니다. 다시 시도해주세요.")

            return data, active_tokens

        raise HTTPException(status_code=401, detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.")

    async def download_file(
        self,
        tokens: StoredTokens,
        *,
        file_id: str,
        mime_type: Optional[str] = None,
    ) -> Tuple[bytes, StoredTokens]:
        active_tokens = tokens
        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {active_tokens.access_token}",
            }
            if mime_type == GOOGLE_SHEETS_MIME_TYPE:
                path = f"{DRIVE_FILES_ENDPOINT}/{file_id}/export"
                params = {"mimeType": XLSX_MIME_TYPE}
            else:
                path = f"{DRIVE_FILES_ENDPOINT}/{file_id}"
                params = {"alt": "media"}

            async with httpx.AsyncClient(timeout=30.0, base_url=DRIVE_API_BASE) as client:
                response = await client.get(
                    path,
                    params=params,
                    headers=headers,
                )

            if response.status_code == 401 and attempt == 0:
                active_tokens = await self.refresh_access_token(active_tokens)
                continue

            if response.is_error:
                logger.error("Google Drive file download failed for %s: %s", file_id, response.text)
                raise HTTPException(
                    status_code=502,
                    detail="Google Drive에서 파일을 다운로드하지 못했습니다. 잠시 후 다시 시도해주세요.",
                )

            return response.content, active_tokens

        raise HTTPException(status_code=401, detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.")

    async def update_file(
        self,
        tokens: StoredTokens,
        *,
        file_id: str,
        file_name: str,
        content: bytes,
        content_type: str,
    ) -> Tuple[Dict[str, Any], StoredTokens]:
        active_tokens = tokens
        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {active_tokens.access_token}",
            }
            metadata = {"name": file_name}
            files = {
                "metadata": (
                    "metadata",
                    json.dumps(metadata),
                    "application/json; charset=UTF-8",
                ),
                "file": (
                    file_name,
                    content,
                    content_type,
                ),
            }

            async with httpx.AsyncClient(timeout=30.0, base_url=DRIVE_UPLOAD_BASE) as client:
                response = await client.patch(
                    f"{DRIVE_FILES_ENDPOINT}/{file_id}?uploadType=multipart&fields=id,name,modifiedTime",
                    headers=headers,
                    files=files,
                )

            if response.status_code == 401 and attempt == 0:
                active_tokens = await self.refresh_access_token(active_tokens)
                continue

            if response.is_error:
                logger.error("Google Drive file update failed for %s: %s", file_id, response.text)
                raise HTTPException(
                    status_code=502,
                    detail="Google Drive 파일을 업데이트하지 못했습니다. 잠시 후 다시 시도해주세요.",
                )

            data = response.json()
            if not isinstance(data, dict) or "id" not in data:
                logger.error("Google Drive file update response missing id: %s", data)
                raise HTTPException(status_code=502, detail="업데이트된 파일 정보를 확인하지 못했습니다. 다시 시도해주세요.")

            return data, active_tokens

        raise HTTPException(status_code=401, detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.")

    async def list_child_folders(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
    ) -> Tuple[Sequence[Dict[str, Any]], StoredTokens]:
        query = (
            f"'{parent_id}' in parents and "
            f"mimeType = '{DRIVE_FOLDER_MIME_TYPE}' and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id,name,createdTime,modifiedTime)",
            "orderBy": "name_natural",
            "spaces": "drive",
            "pageSize": 100,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        data, updated_tokens = await self.request(
            tokens,
            method="GET",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
        )

        files = data.get("files")
        if isinstance(files, Sequence):
            return files, updated_tokens

        return [], updated_tokens

    async def list_child_files(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        mime_type: Optional[str] = None,
    ) -> Tuple[Sequence[Dict[str, Any]], StoredTokens]:
        clauses = [f"'{parent_id}' in parents", "trashed = false"]
        if mime_type:
            clauses.append(f"mimeType = '{mime_type}'")
        params = {
            "q": " and ".join(clauses),
            "fields": "files(id,name,mimeType,modifiedTime)",
            "orderBy": "name_natural",
            "spaces": "drive",
            "pageSize": 100,
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }

        data, updated_tokens = await self.request(
            tokens,
            method="GET",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
        )

        files = data.get("files")
        if isinstance(files, Sequence):
            return files, updated_tokens

        return [], updated_tokens

    async def get_file_metadata(
        self,
        tokens: StoredTokens,
        *,
        file_id: str,
    ) -> Tuple[Optional[Dict[str, Any]], StoredTokens]:
        active_tokens = tokens
        params = {
            "fields": "id,name,mimeType,modifiedTime,parents",
            "supportsAllDrives": "true",
        }
        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {active_tokens.access_token}",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(timeout=10.0, base_url=DRIVE_API_BASE) as client:
                response = await client.get(
                    f"{DRIVE_FILES_ENDPOINT}/{file_id}",
                    params=params,
                    headers=headers,
                )

            if response.status_code == 401 and attempt == 0:
                active_tokens = await self.refresh_access_token(active_tokens)
                continue

            if response.status_code == 404:
                return None, active_tokens

            if response.is_error:
                logger.error("Google Drive metadata fetch failed for %s: %s", file_id, response.text)
                raise HTTPException(
                    status_code=502,
                    detail="Google Drive에서 파일 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.",
                )

            data = response.json() if response.text else {}
            if not isinstance(data, dict):
                logger.error("Google Drive metadata response malformed for %s: %s", file_id, data)
                raise HTTPException(
                    status_code=502,
                    detail="Google Drive 파일 정보를 확인하지 못했습니다. 다시 시도해주세요.",
                )

            return data, active_tokens

        raise HTTPException(status_code=401, detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.")

    async def find_file_by_name(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        name: str,
        mime_type: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], StoredTokens]:
        files, updated_tokens = await self.list_child_files(
            tokens, parent_id=parent_id, mime_type=mime_type
        )
        normalized_name = name.strip()
        for entry in files:
            if not isinstance(entry, dict):
                continue
            file_name = entry.get("name")
            if isinstance(file_name, str) and file_name.strip() == normalized_name:
                return entry, updated_tokens
        return None, updated_tokens

