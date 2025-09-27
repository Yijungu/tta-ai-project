import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'postmessage')

raw_origins = os.getenv('CORS_ALLOW_ORIGINS', '*')
ALLOWED_ORIGINS = [origin.strip() for origin in raw_origins.split(',') if origin.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ['*']

TOKENS_FILE = Path(__file__).resolve().parent / 'google_tokens.json'


class ExchangeRequest(BaseModel):
    code: str = Field(..., description='Google OAuth authorization code')


class TokenStore:
    def __init__(self, filepath: Path):
        self.filepath = filepath

    def save(self, payload: dict[str, Any]) -> None:
        self.filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    def read(self) -> dict[str, Any] | None:
        if not self.filepath.exists():
            return None
        try:
            return json.loads(self.filepath.read_text())
        except json.JSONDecodeError:
            return None


store = TokenStore(TOKENS_FILE)

app = FastAPI(title='Drive Auth Service')

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/')
def read_root() -> dict[str, str]:
    return {
        'project': 'TTA-AI-Project',
        'status': 'running',
    }


@app.get('/auth/google/tokens')
def get_saved_tokens() -> dict[str, Any]:
    saved = store.read()
    if not saved:
        raise HTTPException(status_code=404, detail='저장된 토큰이 없습니다.')
    return saved


@app.post('/auth/google/exchange')
async def exchange_authorization_code(payload: ExchangeRequest) -> dict[str, Any]:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail='Google OAuth 환경 변수가 설정되어 있지 않습니다. 서버 설정을 확인하세요.',
        )

    token_endpoint = 'https://oauth2.googleapis.com/token'
    data = {
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'code': payload.code,
        'grant_type': 'authorization_code',
        'redirect_uri': GOOGLE_REDIRECT_URI,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            token_endpoint,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )

    if response.status_code != 200:
        try:
            error_detail = response.json()
        except ValueError:
            error_detail = {'error': response.text}
        raise HTTPException(status_code=response.status_code, detail=error_detail)

    token_payload = response.json()
    expires_in = int(token_payload.get('expires_in', 0))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    stored_payload = {
        'accessToken': token_payload.get('access_token'),
        'refreshToken': token_payload.get('refresh_token'),
        'expiresAt': expires_at.isoformat(),
        'scope': token_payload.get('scope'),
        'tokenType': token_payload.get('token_type'),
    }

    store.save(stored_payload)

    return stored_payload
