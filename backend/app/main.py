from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.settings import get_settings
from .services.google_drive import DriveService
from .token_store import TokenStorage

logging.basicConfig(level=logging.INFO)

settings = get_settings()
token_storage = TokenStorage(settings.tokens_path)
drive_service = DriveService(settings, token_storage)

app = FastAPI()
app.state.settings = settings
app.state.token_storage = token_storage
app.state.drive_service = drive_service

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin] if settings.frontend_origin != "" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
