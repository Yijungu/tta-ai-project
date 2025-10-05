from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..dependencies import get_prompt_store
from ..services.prompt_store import PromptStore


router = APIRouter(prefix="/admin/prompts", tags=["prompt-admin"])


class PromptResponse(BaseModel):
    menu_id: str
    system: str
    instruction: str


class PromptUpdateRequest(BaseModel):
    system: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)


@router.get("/{menu_id}", response_model=PromptResponse)
def read_prompt(menu_id: str, store: PromptStore = Depends(get_prompt_store)) -> PromptResponse:
    prompt = store.get_prompt(menu_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="해당 메뉴 프롬프트를 찾을 수 없습니다.")
    return PromptResponse(menu_id=menu_id, **prompt)


@router.put("/{menu_id}", response_model=PromptResponse)
def update_prompt(
    menu_id: str,
    payload: PromptUpdateRequest,
    store: PromptStore = Depends(get_prompt_store),
) -> PromptResponse:
    updated = store.update_prompt(
        menu_id,
        {
            "system": payload.system,
            "instruction": payload.instruction,
        },
    )
    return PromptResponse(menu_id=menu_id, **updated)
