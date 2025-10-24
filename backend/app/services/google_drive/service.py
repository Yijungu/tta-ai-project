"""High level Google Drive service built on top of helper modules."""

from __future__ import annotations

import io
import logging
import mimetypes
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException, UploadFile

from ...config import Settings
from ...token_store import StoredTokens, TokenStorage
from ..oauth import GoogleOAuthService
from .client import XLSX_MIME_TYPE, GoogleDriveClient
from .feature_lists import (
    build_feature_list_csv,
    parse_feature_list_workbook,
    populate_workbook as populate_feature_list_workbook,
)
from .metadata import (
    EXAM_NUMBER_PATTERN,
    build_project_folder_name,
    extract_project_metadata,
)
from .naming import drive_name_variants, drive_suffix_matches
from .templates import (
    PLACEHOLDER_PATTERNS,
    PREFERRED_SHARED_CRITERIA_FILE_NAME,
    ResolvedSpreadsheet,
    SHARED_CRITERIA_NORMALIZED_NAMES,
    SPREADSHEET_RULES,
    TEMPLATE_ROOT,
    is_shared_criteria_candidate,
    load_shared_criteria_template_bytes,
    normalize_shared_criteria_name,
)


logger = logging.getLogger(__name__)


class GoogleDriveService:
    """High level operations for interacting with Google Drive."""

    def __init__(
        self,
        settings: Settings,
        token_storage: TokenStorage,
        oauth_service: GoogleOAuthService,
    ) -> None:
        self._client = GoogleDriveClient(settings, token_storage, oauth_service)

    @property
    def client(self) -> GoogleDriveClient:
        return self._client

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _replace_placeholders(text: str, exam_number: str) -> str:
        result = text
        for placeholder in PLACEHOLDER_PATTERNS:
            result = result.replace(placeholder, exam_number)
        return result

    @staticmethod
    def _replace_in_office_document(data: bytes, exam_number: str) -> bytes:
        original = io.BytesIO(data)
        updated = io.BytesIO()
        with zipfile.ZipFile(original, "r") as source_zip:
            with zipfile.ZipFile(updated, "w") as target_zip:
                for item in source_zip.infolist():
                    content = source_zip.read(item.filename)
                    try:
                        decoded = content.decode("utf-8")
                    except UnicodeDecodeError:
                        target_zip.writestr(item, content)
                        continue
                    replaced = GoogleDriveService._replace_placeholders(decoded, exam_number)
                    target_zip.writestr(item, replaced.encode("utf-8"))
        return updated.getvalue()

    @staticmethod
    def _prepare_template_file_content(path: Path, exam_number: str) -> bytes:
        raw_bytes = path.read_bytes()
        extension = path.suffix.lower()
        if extension in {".docx", ".xlsx", ".pptx"}:
            raw_bytes = GoogleDriveService._replace_in_office_document(raw_bytes, exam_number)
        return raw_bytes

    @staticmethod
    def _guess_mime_type(path: Path) -> str:
        mime_type, _ = mimetypes.guess_type(path.name)
        return mime_type or "application/octet-stream"

    async def _copy_template_to_drive(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        exam_number: str,
    ) -> StoredTokens:
        if not TEMPLATE_ROOT.exists():
            raise HTTPException(status_code=500, detail="template 폴더를 찾을 수 없습니다.")

        path_to_folder_id: Dict[Path, str] = {TEMPLATE_ROOT: parent_id}
        active_tokens = tokens
        for root_dir, dirnames, filenames in os.walk(TEMPLATE_ROOT):
            current_path = Path(root_dir)
            drive_parent_id = path_to_folder_id[current_path]

            for dirname in sorted(dirnames):
                local_dir = current_path / dirname
                folder_name = self._replace_placeholders(dirname, exam_number)
                folder, active_tokens = await self._client.create_child_folder(
                    active_tokens,
                    name=folder_name,
                    parent_id=drive_parent_id,
                )
                path_to_folder_id[local_dir] = str(folder["id"])

            for filename in sorted(filenames):
                if is_shared_criteria_candidate(filename):
                    logger.info("Skip copying shared criteria into project: %s", filename)
                    continue

                local_file = current_path / filename
                target_name = self._replace_placeholders(filename, exam_number)
                content = self._prepare_template_file_content(local_file, exam_number)
                mime_type = self._guess_mime_type(local_file)
                _, active_tokens = await self._client.upload_file(
                    active_tokens,
                    file_name=target_name,
                    parent_id=drive_parent_id,
                    content=content,
                    content_type=mime_type,
                )

        return active_tokens

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------
    async def _ensure_tokens(self, google_id: Optional[str]) -> StoredTokens:
        self._client.oauth_service.ensure_credentials()
        stored_tokens = self._client.load_tokens(google_id)
        return await self._client.ensure_valid_tokens(stored_tokens)

    # ------------------------------------------------------------------
    # Spreadsheet resolution helpers
    # ------------------------------------------------------------------
    async def _find_child_folder_by_name(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        name: str,
    ) -> Tuple[Optional[Dict[str, Any]], StoredTokens]:
        folders, updated_tokens = await self._client.list_child_folders(tokens, parent_id=parent_id)
        target_variants = set(drive_name_variants(name))
        for folder in folders:
            if not isinstance(folder, dict):
                continue
            folder_name = folder.get("name")
            if not isinstance(folder_name, str):
                continue
            if folder_name == name:
                return folder, updated_tokens
            if target_variants and set(drive_name_variants(folder_name)) & target_variants:
                return folder, updated_tokens
        return None, updated_tokens

    async def _find_file_by_suffix(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        suffix: str,
        mime_type: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], StoredTokens]:
        search_mime_types: Sequence[Optional[str]]
        if mime_type:
            search_mime_types = (mime_type, None)
        else:
            search_mime_types = (None,)

        updated_tokens = tokens
        for candidate_mime in search_mime_types:
            files, updated_tokens = await self._client.list_child_files(
                updated_tokens,
                parent_id=parent_id,
                mime_type=candidate_mime,
            )
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if isinstance(name, str):
                    if name.endswith(suffix.strip()) or drive_suffix_matches(name, suffix):
                        return entry, updated_tokens
        return None, updated_tokens

    async def _resolve_menu_spreadsheet(
        self,
        *,
        project_id: str,
        menu_id: str,
        google_id: Optional[str],
        include_content: bool = False,
        file_id: Optional[str] = None,
    ) -> ResolvedSpreadsheet:
        rule = SPREADSHEET_RULES.get(menu_id)
        if not rule:
            raise HTTPException(status_code=404, detail="지원하지 않는 스프레드시트 메뉴입니다.")

        active_tokens = await self._ensure_tokens(google_id)

        folder, active_tokens = await self._find_child_folder_by_name(
            active_tokens,
            parent_id=project_id,
            name=rule["folder_name"],
        )
        if folder is None or not folder.get("id"):
            raise HTTPException(status_code=404, detail=f"프로젝트에 '{rule['folder_name']}' 폴더를 찾을 수 없습니다.")

        folder_id = str(folder["id"])
        file_entry: Optional[Dict[str, Any]] = None
        if file_id:
            file_entry, active_tokens = await self._client.get_file_metadata(
                active_tokens,
                file_id=file_id,
            )
            if file_entry is None or not file_entry.get("id"):
                raise HTTPException(status_code=404, detail=f"프로젝트에 '{rule['file_suffix']}' 파일을 찾을 수 없습니다.")

            parents = file_entry.get("parents")
            if isinstance(parents, Sequence) and parents:
                parent_ids = {
                    parent.decode("utf-8") if isinstance(parent, bytes) else str(parent)
                    for parent in parents
                    if isinstance(parent, (str, bytes))
                }
                if folder_id not in parent_ids:
                    logger.warning(
                        "Drive file is outside expected folder",
                        extra={
                            "project_id": project_id,
                            "menu_id": menu_id,
                            "expected_folder_id": folder_id,
                            "file_parents": list(parent_ids),
                            "file_id": file_id,
                        },
                    )
        else:
            file_entry, active_tokens = await self._find_file_by_suffix(
                active_tokens,
                parent_id=folder_id,
                suffix=rule["file_suffix"],
                mime_type=XLSX_MIME_TYPE,
            )
            if file_entry is None or not file_entry.get("id"):
                raise HTTPException(status_code=404, detail=f"프로젝트에 '{rule['file_suffix']}' 파일을 찾을 수 없습니다.")

        file_id = str(file_entry["id"])
        file_name = str(file_entry.get("name", rule["file_suffix"]))
        mime_type = file_entry.get("mimeType")
        normalized_mime = mime_type if isinstance(mime_type, str) else None
        modified_time = (
            str(file_entry.get("modifiedTime"))
            if isinstance(file_entry.get("modifiedTime"), str)
            else None
        )

        content: Optional[bytes] = None
        if include_content:
            content, active_tokens = await self._client.download_file(
                active_tokens,
                file_id=file_id,
                mime_type=normalized_mime,
            )

        return ResolvedSpreadsheet(
            rule=rule,
            tokens=active_tokens,
            folder_id=folder_id,
            file_id=file_id,
            file_name=file_name,
            mime_type=normalized_mime,
            modified_time=modified_time,
            content=content,
        )

    # ------------------------------------------------------------------
    # Public workflows
    # ------------------------------------------------------------------
    async def ensure_drive_setup(self, google_id: Optional[str]) -> Dict[str, Any]:
        active_tokens = await self._ensure_tokens(google_id)

        folder, active_tokens = await self._client.find_root_folder(active_tokens, folder_name="gs")
        folder_created = False

        if folder is None:
            folder, active_tokens = await self._client.create_root_folder(active_tokens, folder_name="gs")
            folder_created = True

        gs_folder_id = str(folder["id"])

        criteria_sheet, active_tokens, criteria_created = await self._ensure_shared_criteria_file(
            active_tokens,
            parent_id=gs_folder_id,
        )

        projects, active_tokens = await self._client.list_child_folders(
            active_tokens, parent_id=str(folder["id"])
        )

        normalized_projects = []
        for item in projects:
            if not isinstance(item, dict):
                continue
            project_id = item.get("id")
            name = item.get("name")
            if not isinstance(project_id, str) or not isinstance(name, str):
                continue
            normalized_projects.append(
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
            "criteria": {
                "created": criteria_created,
                "fileId": criteria_sheet.get("id"),
                "fileName": criteria_sheet.get("name"),
                "mimeType": criteria_sheet.get("mimeType"),
            },
            "projects": normalized_projects,
            "account": {
                "googleId": active_tokens.google_id,
                "displayName": active_tokens.display_name,
                "email": active_tokens.email,
            },
        }

    async def create_project(
        self,
        *,
        folder_id: Optional[str],
        files: List[UploadFile],
        google_id: Optional[str],
    ) -> Dict[str, Any]:
        active_tokens = await self._ensure_tokens(google_id)

        parent_folder_id = folder_id
        if not parent_folder_id:
            folder, active_tokens = await self._client.find_root_folder(active_tokens, folder_name="gs")
            if folder is None:
                folder, active_tokens = await self._client.create_root_folder(active_tokens, folder_name="gs")
            parent_folder_id = str(folder["id"])

        agreement_file = files[0]
        if not agreement_file.filename or not agreement_file.filename.lower().endswith(".docx"):
            raise HTTPException(status_code=422, detail="시험 합의서는 DOCX 파일이어야 합니다.")

        agreement_bytes = await agreement_file.read()
        metadata = extract_project_metadata(agreement_bytes)
        project_name = build_project_folder_name(metadata)
        if not project_name:
            raise HTTPException(status_code=422, detail="생성할 프로젝트 이름을 결정할 수 없습니다.")

        siblings, active_tokens = await self._client.list_child_folders(
            active_tokens, parent_id=parent_folder_id
        )
        existing_names = {
            str(item.get("name"))
            for item in siblings
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }

        unique_name = project_name
        suffix = 1
        while unique_name in existing_names:
            suffix += 1
            unique_name = f"{project_name} ({suffix})"

        project_folder, active_tokens = await self._client.create_child_folder(
            active_tokens,
            name=unique_name,
            parent_id=parent_folder_id,
        )
        project_id = str(project_folder["id"])

        active_tokens = await self._copy_template_to_drive(
            active_tokens,
            parent_id=project_id,
            exam_number=metadata["exam_number"],
        )

        uploaded_files: List[Dict[str, Any]] = []

        agreement_name = agreement_file.filename or "시험 합의서.docx"
        agreement_name = self._replace_placeholders(agreement_name, metadata["exam_number"])
        file_info, active_tokens = await self._client.upload_file(
            active_tokens,
            file_name=agreement_name,
            parent_id=project_id,
            content=agreement_bytes,
            content_type=agreement_file.content_type
            or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        uploaded_files.append(
            {
                "id": file_info.get("id"),
                "name": file_info.get("name", agreement_name),
                "size": len(agreement_bytes),
                "contentType": agreement_file.content_type
                or "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        )
        await agreement_file.close()

        for upload in files[1:]:
            filename = upload.filename or "업로드된 파일.docx"
            content = await upload.read()
            file_info, active_tokens = await self._client.upload_file(
                active_tokens,
                file_name=filename,
                parent_id=project_id,
                content=content,
                content_type=upload.content_type,
            )
            uploaded_files.append(
                {
                    "id": file_info.get("id"),
                    "name": file_info.get("name", filename),
                    "size": len(content),
                    "contentType": upload.content_type or "application/octet-stream",
                }
            )
            await upload.close()

        logger.info(
            "Created Drive project '%s' (%s) with metadata %s",
            unique_name,
            project_id,
            metadata,
        )

        return {
            "message": "새 프로젝트 폴더를 생성했습니다.",
            "project": {
                "id": project_id,
                "name": project_folder.get("name", unique_name),
                "parentId": parent_folder_id,
                "metadata": {
                    "examNumber": metadata["exam_number"],
                    "companyName": metadata["company_name"],
                    "productName": metadata["product_name"],
                },
            },
            "uploadedFiles": uploaded_files,
        }

    async def apply_csv_to_spreadsheet(
        self,
        *,
        project_id: str,
        menu_id: str,
        csv_text: str,
        google_id: Optional[str],
        project_overview: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if menu_id not in SPREADSHEET_RULES:
            return None

        resolved = await self._resolve_menu_spreadsheet(
            project_id=project_id,
            menu_id=menu_id,
            google_id=google_id,
            include_content=True,
        )

        workbook_bytes = resolved.content
        if workbook_bytes is None:
            raise HTTPException(status_code=500, detail="스프레드시트 내용을 불러오지 못했습니다. 다시 시도해 주세요.")

        overview_value: Optional[str] = None
        try:
            populate = resolved.rule["populate"]
            if menu_id == "feature-list":
                overview_value = str(project_overview or "") if project_overview is not None else None
                updated_bytes = populate(workbook_bytes, csv_text, overview_value)
            else:
                updated_bytes = populate(workbook_bytes, csv_text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception(
                "Failed to populate spreadsheet for project",
                extra={"project_id": project_id, "menu_id": menu_id},
            )
            raise HTTPException(status_code=500, detail="엑셀 템플릿을 업데이트하지 못했습니다. 다시 시도해주세요.") from exc

        update_info, _ = await self._client.update_file(
            resolved.tokens,
            file_id=resolved.file_id,
            file_name=resolved.file_name,
            content=updated_bytes,
            content_type=XLSX_MIME_TYPE,
        )
        logger.info(
            "Populated project spreadsheet",
            extra={"project_id": project_id, "menu_id": menu_id, "file_id": resolved.file_id},
        )
        response: Dict[str, Any] = {
            "fileId": resolved.file_id,
            "fileName": resolved.file_name,
            "modifiedTime": update_info.get("modifiedTime") if isinstance(update_info, dict) else None,
        }
        if menu_id == "feature-list" and overview_value is not None:
            response["projectOverview"] = overview_value
        return response

    async def get_feature_list_rows(
        self,
        *,
        project_id: str,
        google_id: Optional[str],
        file_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved = await self._resolve_menu_spreadsheet(
            project_id=project_id,
            menu_id="feature-list",
            google_id=google_id,
            include_content=True,
            file_id=file_id,
        )

        workbook_bytes = resolved.content
        if workbook_bytes is None:
            raise HTTPException(status_code=500, detail="기능리스트 파일을 불러오지 못했습니다. 다시 시도해 주세요.")

        context, rows = parse_feature_list_workbook(workbook_bytes)

        return {
            "fileId": resolved.file_id,
            "fileName": resolved.file_name,
            "sheetName": context["sheetName"],
            "startRow": context["startRow"],
            "headers": context["headers"],
            "rows": rows,
            "modifiedTime": resolved.modified_time,
            "projectOverview": context["projectOverview"],
        }

    async def update_feature_list_rows(
        self,
        *,
        project_id: str,
        rows: Sequence[Dict[str, str]],
        project_overview: str = "",
        google_id: Optional[str],
        file_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        resolved = await self._resolve_menu_spreadsheet(
            project_id=project_id,
            menu_id="feature-list",
            google_id=google_id,
            include_content=True,
            file_id=file_id,
        )

        workbook_bytes = resolved.content
        if workbook_bytes is None:
            raise HTTPException(status_code=500, detail="기능리스트 파일을 불러오지 못했습니다. 다시 시도해 주세요.")

        csv_text = build_feature_list_csv(rows)

        try:
            updated_bytes = populate_feature_list_workbook(
                workbook_bytes,
                csv_text,
                project_overview,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception(
                "Failed to update feature list spreadsheet", extra={"project_id": project_id}
            )
            raise HTTPException(status_code=500, detail="기능리스트를 업데이트하지 못했습니다. 다시 시도해 주세요.") from exc

        update_info, _ = await self._client.update_file(
            resolved.tokens,
            file_id=resolved.file_id,
            file_name=resolved.file_name,
            content=updated_bytes,
            content_type=XLSX_MIME_TYPE,
        )

        return {
            "fileId": resolved.file_id,
            "fileName": resolved.file_name,
            "modifiedTime": update_info.get("modifiedTime") if isinstance(update_info, dict) else None,
            "projectOverview": project_overview,
        }

    async def download_feature_list_workbook(
        self,
        *,
        project_id: str,
        google_id: Optional[str],
        file_id: Optional[str] = None,
    ) -> Tuple[str, bytes]:
        resolved = await self._resolve_menu_spreadsheet(
            project_id=project_id,
            menu_id="feature-list",
            google_id=google_id,
            include_content=True,
            file_id=file_id,
        )

        workbook_bytes = resolved.content
        if workbook_bytes is None:
            raise HTTPException(status_code=500, detail="기능리스트 파일을 불러오지 못했습니다. 다시 시도해 주세요.")

        return resolved.file_name, workbook_bytes

    async def get_project_exam_number(
        self,
        *,
        project_id: str,
        google_id: Optional[str],
    ) -> str:
        active_tokens = await self._ensure_tokens(google_id)

        params = {"fields": "id,name"}
        data, _ = await self._client.request(
            active_tokens,
            method="GET",
            path=f"/files/{project_id}",
            params=params,
        )

        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(status_code=404, detail="프로젝트 폴더를 찾을 수 없습니다.")

        match = EXAM_NUMBER_PATTERN.search(name)
        if not match:
            raise HTTPException(status_code=404, detail="프로젝트 이름에서 시험신청 번호를 찾을 수 없습니다.")

        return match.group(0)

    async def download_shared_security_criteria(
        self,
        *,
        google_id: Optional[str],
        file_name: str,
    ) -> bytes:
        active_tokens = await self._ensure_tokens(google_id)

        folder, active_tokens = await self._client.find_root_folder(active_tokens, folder_name="gs")
        if folder is None:
            folder, active_tokens = await self._client.create_root_folder(active_tokens, folder_name="gs")
        gs_folder_id = str(folder["id"])

        file_entry, active_tokens, _ = await self._ensure_shared_criteria_file(
            active_tokens,
            parent_id=gs_folder_id,
            preferred_names=(file_name,),
        )

        file_id = file_entry.get("id")
        if not isinstance(file_id, str):
            logger.error("Shared criteria entry missing id: %s", file_entry)
            raise HTTPException(status_code=502, detail="결함 판단 기준표 ID를 확인할 수 없습니다.")

        content, _ = await self._client.download_file(
            active_tokens,
            file_id=file_id,
            mime_type=file_entry.get("mimeType"),
        )
        return content

    # ------------------------------------------------------------------
    # Shared criteria helpers
    # ------------------------------------------------------------------
    async def _ensure_shared_criteria_file(
        self,
        tokens: StoredTokens,
        *,
        parent_id: str,
        preferred_names: Optional[Sequence[str]] = None,
    ) -> Tuple[Dict[str, Any], StoredTokens, bool]:
        normalized_candidates = set(SHARED_CRITERIA_NORMALIZED_NAMES)
        upload_name = PREFERRED_SHARED_CRITERIA_FILE_NAME
        if preferred_names:
            normalized_candidates.update(
                normalize_shared_criteria_name(name)
                for name in preferred_names
                if isinstance(name, str) and name.strip()
            )
            first_valid = next(
                (name.strip() for name in preferred_names if isinstance(name, str) and name.strip()),
                None,
            )
            if first_valid:
                upload_name = first_valid

        files, active_tokens = await self._client.list_child_files(
            tokens,
            parent_id=parent_id,
            mime_type=XLSX_MIME_TYPE,
        )

        for entry in files:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            mime_type = entry.get("mimeType")
            if not isinstance(name, str):
                continue
            try:
                normalized = normalize_shared_criteria_name(name)
            except Exception:
                continue
            if normalized in normalized_candidates:
                normalized_entry = dict(entry)
                normalized_entry["mimeType"] = mime_type if isinstance(mime_type, str) else None
                return normalized_entry, active_tokens, False

        content = load_shared_criteria_template_bytes()
        uploaded_entry, updated_tokens = await self._client.upload_file(
            active_tokens,
            file_name=upload_name,
            parent_id=parent_id,
            content=content,
            content_type=XLSX_MIME_TYPE,
        )
        uploaded_entry = dict(uploaded_entry)
        uploaded_entry.setdefault("name", upload_name)
        uploaded_entry["mimeType"] = XLSX_MIME_TYPE
        logger.info(
            "Uploaded shared criteria template to gs folder: %s",
            uploaded_entry.get("name"),
        )
        return uploaded_entry, updated_tokens, True

