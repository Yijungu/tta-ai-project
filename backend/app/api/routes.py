from __future__ import annotations

import secrets
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..core.settings import Settings, get_settings
from ..services.google_auth import build_frontend_redirect
from ..services.google_drive import DriveService
from ..token_store import TokenStorage

router = APIRouter()
state_store: set[str] = set()


def get_token_storage(request: Request) -> TokenStorage:
    return request.app.state.token_storage


def get_drive_service(request: Request) -> DriveService:
    return request.app.state.drive_service


def require_settings() -> Settings:
    settings = get_settings()
    try:
        settings.require_google_credentials()
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return settings


@router.get("/")
def read_root() -> dict[str, str]:
    return {"project": "TTA-AI-Project", "status": "running"}


@router.get("/auth/google/login")
def google_login(settings: Settings = Depends(require_settings)) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    state_store.add(state)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(settings.google_scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    query = httpx.QueryParams(params)
    return RedirectResponse(f"{auth_url}?{query}")


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    settings: Settings = Depends(require_settings),
    storage: TokenStorage = Depends(get_token_storage),
) -> RedirectResponse:
    params = request.query_params
    error = params.get("error")
    state = params.get("state")

    if error:
        message = params.get("error_description", "Google 인증이 취소되었습니다.")
        redirect_url = build_frontend_redirect(settings, "error", message)
        return RedirectResponse(redirect_url)

    code = params.get("code")
    if not code or not state:
        raise HTTPException(status_code=400, detail="code 또는 state 매개변수가 누락되었습니다.")

    if state not in state_store:
        raise HTTPException(status_code=400, detail="유효하지 않은 state 값입니다.")

    state_store.discard(state)

    data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post("https://oauth2.googleapis.com/token", data=data)

    if response.is_error:
        redirect_url = build_frontend_redirect(settings, "error", "Google 토큰 발급에 실패했습니다.")
        return RedirectResponse(redirect_url)

    tokens = response.json()

    access_token = tokens.get("access_token")
    if not access_token:
        redirect_url = build_frontend_redirect(settings, "error", "Google 토큰 발급에 실패했습니다.")
        return RedirectResponse(redirect_url)

    async with httpx.AsyncClient(timeout=10.0) as client:
        userinfo_response = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_response.is_error:
        redirect_url = build_frontend_redirect(
            settings, "error", "Google 사용자 정보를 불러오지 못했습니다. 다시 시도해주세요."
        )
        return RedirectResponse(redirect_url)

    userinfo = userinfo_response.json()
    google_id = userinfo.get("sub")
    display_name = userinfo.get("name") or userinfo.get("email") or "알 수 없는 사용자"
    email = userinfo.get("email")

    if not google_id:
        redirect_url = build_frontend_redirect(
            settings, "error", "Google 사용자 식별자를 확인할 수 없습니다."
        )
        return RedirectResponse(redirect_url)

    storage.save(
        google_id=google_id,
        display_name=display_name,
        email=email,
        payload=tokens,
    )

    redirect_url = build_frontend_redirect(
        settings,
        "success",
        message=f"{display_name} 계정의 토큰이 저장되었습니다.",
    )
    return RedirectResponse(redirect_url)


@router.get("/auth/google/tokens")
def read_tokens(
    google_id: Optional[str] = Query(None, description="조회할 Google 사용자 식별자 (sub)"),
    email: Optional[str] = Query(None, description="조회할 Google 계정 이메일"),
    _settings: Settings = Depends(require_settings),
    storage: TokenStorage = Depends(get_token_storage),
) -> JSONResponse:
    if not google_id and not email:
        raise HTTPException(
            status_code=400,
            detail="google_id 또는 email 중 하나는 반드시 제공해야 합니다.",
        )

    stored = None
    if google_id:
        stored = storage.load_by_google_id(google_id)
    if stored is None and email:
        stored = storage.load_by_email(email)
    if not stored:
        raise HTTPException(status_code=404, detail="요청한 사용자에 대한 저장된 토큰이 없습니다.")

    payload = stored.to_dict()
    payload.pop("access_token", None)
    payload.pop("refresh_token", None)

    return JSONResponse(payload)


@router.get("/auth/google/users")
def list_users(
    _settings: Settings = Depends(require_settings),
    storage: TokenStorage = Depends(get_token_storage),
) -> JSONResponse:
    accounts = [account.to_dict() for account in storage.list_accounts()]
    return JSONResponse(accounts)


@router.post("/drive/gs/setup")
async def ensure_gs_folder(
    google_id: Optional[str] = Query(
        None,
        description="Drive 작업에 사용할 Google 사용자 식별자 (sub)",
    ),
    _settings: Settings = Depends(require_settings),
    service: DriveService = Depends(get_drive_service),
) -> JSONResponse:
    result = await service.ensure_project_root(google_id)
    return JSONResponse(result)


@router.post("/drive/projects")
async def create_drive_project(
    folder_id: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    allowed_types: Optional[List[str]] = Form(None),
    google_id: Optional[str] = Query(
        None,
        description="Drive 작업에 사용할 Google 사용자 식별자 (sub)",
    ),
    _settings: Settings = Depends(require_settings),
    service: DriveService = Depends(get_drive_service),
) -> dict:
    result = await service.create_project(
        google_id,
        files,
        folder_id=folder_id,
        allowed_types=allowed_types,
    )
    return result


@router.get("/auth/google/callback/success")
def success_page() -> HTMLResponse:
    return HTMLResponse(
        """
        <html>
            <head>
                <meta charset=\"utf-8\" />
                <title>Google 인증 완료</title>
                <style>
                    body { font-family: sans-serif; padding: 48px; text-align: center; }
                    h1 { color: #2563eb; }
                </style>
            </head>
            <body>
                <h1>Google Drive 인증이 완료되었습니다.</h1>
                <p>이 창은 닫으셔도 됩니다.</p>
            </body>
        </html>
        """
    )
