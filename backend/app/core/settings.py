from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _resolve_tokens_path() -> Path:
    tokens_path_env = os.getenv("GOOGLE_TOKEN_DB_PATH") or os.getenv("GOOGLE_TOKEN_PATH")
    default_tokens_path = Path(__file__).resolve().parent.parent / "google_tokens.db"
    return Path(tokens_path_env) if tokens_path_env else default_tokens_path


PROJECT_SUBFOLDERS: Tuple[str, ...] = (
    "0. 사전 자료",
    "1. 형상 사진",
    "2. 기능리스트",
    "3. 테스트케이스",
    "4. 성능 시험",
    "5. 보안성 시험",
    "6. 결함리포트",
    "7. 산출물",
)


@dataclass(frozen=True)
class Settings:
    google_client_id: str | None
    google_client_secret: str | None
    google_redirect_uri: str | None
    frontend_redirect_url: str
    tokens_path: Path

    google_scopes: Tuple[str, ...] = (
        "openid",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.file",
    )

    drive_api_base: str = "https://www.googleapis.com/drive/v3"
    drive_upload_base: str = "https://www.googleapis.com/upload/drive/v3"
    drive_folder_mime_type: str = "application/vnd.google-apps.folder"
    project_folder_base_name: str = "GS-X-X-XXXX"
    project_subfolders: Tuple[str, ...] = PROJECT_SUBFOLDERS

    def require_google_credentials(self) -> None:
        if not (self.google_client_id and self.google_client_secret and self.google_redirect_uri):
            raise ValueError("Google OAuth 환경 변수가 올바르게 설정되지 않았습니다.")

    @property
    def frontend_origin(self) -> str:
        parsed = urlparse(self.frontend_redirect_url)
        if not parsed.scheme or not parsed.netloc:
            return "*"
        return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        google_client_id=os.getenv("GOOGLE_CLIENT_ID"),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=os.getenv("GOOGLE_REDIRECT_URI"),
        frontend_redirect_url=os.getenv("FRONTEND_REDIRECT_URL", "http://localhost:5173/"),
        tokens_path=_resolve_tokens_path(),
    )
