from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_ai_generation_service, get_prompt_store
from ..services.ai_generation import AIGenerationService
from ..services.prompt_store import PromptStore


router = APIRouter(prefix="/admin/prompts", tags=["prompt-admin"])


class PromptAttachmentResponse(BaseModel):
    name: str
    label: str
    role: str
    builtin: bool
    size_bytes: int | None = None
    content_type: str | None = None


class PromptPreviewResponse(BaseModel):
    user_prompt: str
    descriptor_lines: list[str]
    closing_note: str | None = None


class PromptResponse(BaseModel):
    menu_id: str
    system: str
    instruction: str
    attachments: list[PromptAttachmentResponse]
    preview: PromptPreviewResponse


class PromptUpdateRequest(BaseModel):
    system: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)


def _build_response(
    menu_id: str,
    prompt: dict[str, str],
    ai_service: AIGenerationService,
) -> PromptResponse:
    attachments = [
        PromptAttachmentResponse(
            name=attachment.name,
            label=attachment.label,
            role=attachment.role,
            builtin=attachment.builtin,
            size_bytes=attachment.size_bytes,
            content_type=attachment.content_type,
        )
        for attachment in ai_service.describe_builtin_attachments(menu_id)
    ]
    preview = ai_service.describe_prompt_preview(
        menu_id, prompt.get("instruction", "")
    )
    return PromptResponse(
        menu_id=menu_id,
        system=prompt.get("system", ""),
        instruction=prompt.get("instruction", ""),
        attachments=attachments,
        preview=PromptPreviewResponse(
            user_prompt=preview.user_prompt,
            descriptor_lines=preview.descriptor_lines,
            closing_note=preview.closing_note,
        ),
    )


@router.get("/{menu_id}", response_model=PromptResponse)
def read_prompt(
    menu_id: str,
    store: PromptStore = Depends(get_prompt_store),
    ai_service: AIGenerationService = Depends(get_ai_generation_service),
) -> PromptResponse:
    prompt = store.get_prompt(menu_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="해당 메뉴 프롬프트를 찾을 수 없습니다.")
    return _build_response(menu_id, prompt, ai_service)


@router.put("/{menu_id}", response_model=PromptResponse)
def update_prompt(
    menu_id: str,
    payload: PromptUpdateRequest,
    store: PromptStore = Depends(get_prompt_store),
    ai_service: AIGenerationService = Depends(get_ai_generation_service),
) -> PromptResponse:
    updated = store.update_prompt(
        menu_id,
        {
            "system": payload.system,
            "instruction": payload.instruction,
        },
    )
    return _build_response(menu_id, updated, ai_service)
