from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from fastapi import HTTPException, UploadFile

from ..core.settings import Settings
from ..schemas.drive import infer_file_type, is_allowed_filename, normalise_file_types, resolve_content_type
from ..token_store import TokenStorage
from .google_auth import ensure_valid_tokens, load_tokens_for_drive, refresh_access_token

logger = logging.getLogger(__name__)

DRIVE_FILES_ENDPOINT = "/files"


class DriveService:
    def __init__(self, settings: Settings, storage: TokenStorage) -> None:
        self._settings = settings
        self._storage = storage

    async def ensure_project_root(self, google_id: Optional[str]) -> Dict[str, Any]:
        stored_tokens = load_tokens_for_drive(self._storage, google_id)
        active_tokens = await ensure_valid_tokens(self._settings, self._storage, stored_tokens)

        folder, active_tokens = await self._find_root_folder(active_tokens, folder_name="gs")
        folder_created = False

        if folder is None:
            folder, active_tokens = await self._create_root_folder(active_tokens, folder_name="gs")
            folder_created = True

        projects, active_tokens = await self._list_child_folders(
            active_tokens,
            parent_id=str(folder["id"]),
        )

        normalised_projects = []
        for item in projects:
            if not isinstance(item, dict):
                continue
            project_id = item.get("id")
            name = item.get("name")
            if not isinstance(project_id, str) or not isinstance(name, str):
                continue
            normalised_projects.append(
                {
                    "id": project_id,
                    "name": name,
                    "createdTime": item.get("createdTime"),
                    "modifiedTime": item.get("modifiedTime"),
                }
            )

        return {
            "folderCreated": folder_created,
            "folderId": folder["id"],
            "folderName": folder.get("name", "gs"),
            "projects": normalised_projects,
            "account": {
                "googleId": active_tokens.google_id,
                "displayName": active_tokens.display_name,
                "email": active_tokens.email,
            },
        }

    async def create_project(
        self,
        google_id: Optional[str],
        uploads: Iterable[UploadFile],
        *,
        folder_id: Optional[str],
        allowed_types: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        files = list(uploads)
        if not files:
            raise HTTPException(status_code=422, detail="업로드할 파일을 선택해주세요.")

        allowed_file_types = normalise_file_types(allowed_types)
        invalid_files: List[str] = []
        for upload in files:
            filename = upload.filename or "업로드된 파일"
            if not is_allowed_filename(filename, allowed_file_types):
                invalid_files.append(filename)

        if invalid_files:
            detail = ", ".join(invalid_files)
            allowed_names = ", ".join(item.value.upper() for item in allowed_file_types)
            raise HTTPException(
                status_code=422,
                detail=f"허용된 형식({allowed_names})의 파일만 업로드할 수 있습니다: {detail}",
            )

        stored_tokens = load_tokens_for_drive(self._storage, google_id)
        active_tokens = await ensure_valid_tokens(self._settings, self._storage, stored_tokens)

        parent_folder_id = folder_id
        if not parent_folder_id:
            folder, active_tokens = await self._find_root_folder(active_tokens, folder_name="gs")
            if folder is None:
                folder, active_tokens = await self._create_root_folder(active_tokens, folder_name="gs")
            parent_folder_id = str(folder["id"])

        siblings, active_tokens = await self._list_child_folders(
            active_tokens,
            parent_id=parent_folder_id,
        )
        existing_names = {
            str(item.get("name"))
            for item in siblings
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }

        project_name = self._settings.project_folder_base_name
        suffix = 1
        while project_name in existing_names:
            suffix += 1
            project_name = f"{self._settings.project_folder_base_name} ({suffix})"

        project_folder, active_tokens = await self._create_child_folder(
            active_tokens,
            name=project_name,
            parent_id=parent_folder_id,
        )
        project_id = str(project_folder["id"])

        created_subfolders: List[Dict[str, Any]] = []
        upload_target_id: Optional[str] = None

        for index, subfolder_name in enumerate(self._settings.project_subfolders):
            subfolder, active_tokens = await self._create_child_folder(
                active_tokens,
                name=subfolder_name,
                parent_id=str(project_folder["id"]),
            )
            created_subfolders.append(
                {
                    "id": str(subfolder["id"]),
                    "name": subfolder.get("name", subfolder_name),
                }
            )
            if index == 0:
                upload_target_id = str(subfolder["id"])

        if upload_target_id is None:
            upload_target_id = project_id

        uploaded_files: List[Dict[str, Any]] = []
        for upload in files:
            original_name = upload.filename
            fallback_type = (
                infer_file_type(original_name, allowed_file_types)
                if original_name
                else allowed_file_types[0]
            )
            file_name = original_name or f"업로드된 파일.{fallback_type.value}"
            content = await upload.read()
            file_type = infer_file_type(file_name, allowed_file_types)
            file_info, active_tokens = await self._upload_file_to_folder(
                active_tokens,
                file_name=file_name,
                parent_id=upload_target_id,
                content=content,
                content_type=resolve_content_type(upload.content_type, file_type),
            )
            uploaded_files.append(
                {
                    "id": file_info.get("id"),
                    "name": file_info.get("name", file_name),
                    "size": len(content),
                    "contentType": resolve_content_type(upload.content_type, file_type),
                }
            )
            await upload.close()

        logger.info(
            "Created Drive project '%s' (%s) with %d files", project_name, project_id, len(uploaded_files)
        )

        return {
            "message": "새 프로젝트 폴더를 생성했습니다.",
            "project": {
                "id": project_id,
                "name": project_folder.get("name", project_name),
                "parentId": parent_folder_id,
                "subfolders": created_subfolders,
            },
            "uploadedFiles": uploaded_files,
        }

    async def _drive_request(
        self,
        tokens,
        *,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Any]:
        current_tokens = tokens

        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {current_tokens.access_token}",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient(timeout=10.0, base_url=self._settings.drive_api_base) as client:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )

            if response.status_code != 401:
                if response.is_error:
                    logger.error(
                        "Google Drive API %s %s failed: %s", method, path, response.text
                    )
                    raise HTTPException(
                        status_code=502,
                        detail="Google Drive API 요청이 실패했습니다. 잠시 후 다시 시도해주세요.",
                    )

                data = response.json()
                return data, current_tokens

            if attempt == 0:
                current_tokens = await refresh_access_token(self._settings, self._storage, current_tokens)
                continue

        raise HTTPException(
            status_code=401,
            detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.",
        )

    async def _find_root_folder(
        self, tokens, *, folder_name: str
    ) -> Tuple[Optional[Dict[str, Any]], Any]:
        escaped_name = folder_name.replace("'", "\\'")
        query = (
            f"name = '{escaped_name}' and "
            f"mimeType = '{self._settings.drive_folder_mime_type}' and "
            "'root' in parents and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id,name)",
            "pageSize": 1,
            "spaces": "drive",
        }

        data, updated_tokens = await self._drive_request(
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

    async def _create_root_folder(
        self, tokens, *, folder_name: str
    ) -> Tuple[Dict[str, Any], Any]:
        body = {
            "name": folder_name,
            "mimeType": self._settings.drive_folder_mime_type,
            "parents": ["root"],
        }
        params = {"fields": "id,name"}

        data, updated_tokens = await self._drive_request(
            tokens,
            method="POST",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
            json_body=body,
        )

        if not isinstance(data, dict) or "id" not in data:
            logger.error("Google Drive create folder response missing id: %s", data)
            raise HTTPException(
                status_code=502,
                detail="Google Drive 폴더를 생성하지 못했습니다. 다시 시도해주세요.",
            )

        return data, updated_tokens

    async def _create_child_folder(
        self,
        tokens,
        *,
        name: str,
        parent_id: str,
    ) -> Tuple[Dict[str, Any], Any]:
        body = {
            "name": name,
            "mimeType": self._settings.drive_folder_mime_type,
            "parents": [parent_id],
        }
        params = {"fields": "id,name,parents"}

        data, updated_tokens = await self._drive_request(
            tokens,
            method="POST",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
            json_body=body,
        )

        if not isinstance(data, dict) or "id" not in data:
            logger.error("Google Drive create child folder response missing id: %s", data)
            raise HTTPException(
                status_code=502,
                detail="Google Drive 하위 폴더를 생성하지 못했습니다. 다시 시도해주세요.",
            )

        return data, updated_tokens

    async def _upload_file_to_folder(
        self,
        tokens,
        *,
        file_name: str,
        parent_id: str,
        content: bytes,
        content_type: str,
    ) -> Tuple[Dict[str, Any], Any]:
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
                    content_type,
                ),
            }

            async with httpx.AsyncClient(timeout=30.0, base_url=self._settings.drive_upload_base) as client:
                response = await client.post(
                    f"{DRIVE_FILES_ENDPOINT}?uploadType=multipart&fields=id,name,parents",
                    headers=headers,
                    files=files,
                )

            if response.status_code == 401 and attempt == 0:
                active_tokens = await refresh_access_token(self._settings, self._storage, active_tokens)
                continue

            if response.is_error:
                logger.error(
                    "Google Drive file upload failed for %s: %s",
                    file_name,
                    response.text,
                )
                raise HTTPException(
                    status_code=502,
                    detail="파일을 Google Drive에 업로드하지 못했습니다. 잠시 후 다시 시도해주세요.",
                )

            data = response.json()
            if not isinstance(data, dict) or "id" not in data:
                logger.error("Google Drive file upload response missing id: %s", data)
                raise HTTPException(
                    status_code=502,
                    detail="업로드한 파일의 ID를 확인하지 못했습니다. 다시 시도해주세요.",
                )

            return data, active_tokens

        raise HTTPException(
            status_code=401,
            detail="Google Drive 인증이 만료되었습니다. 다시 로그인해주세요.",
        )

    async def _list_child_folders(
        self,
        tokens,
        *,
        parent_id: str,
    ) -> Tuple[Sequence[Dict[str, Any]], Any]:
        query = (
            f"'{parent_id}' in parents and "
            f"mimeType = '{self._settings.drive_folder_mime_type}' and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id,name,createdTime,modifiedTime)",
            "orderBy": "name_natural",
            "spaces": "drive",
            "pageSize": 100,
        }

        data, updated_tokens = await self._drive_request(
            tokens,
            method="GET",
            path=DRIVE_FILES_ENDPOINT,
            params=params,
        )

        files = data.get("files")
        if isinstance(files, Sequence):
            return files, updated_tokens

        return [], updated_tokens
