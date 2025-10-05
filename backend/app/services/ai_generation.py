from __future__ import annotations

import asyncio
import base64
import io
import logging
import mimetypes
import os
import re
import zipfile
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Literal
from xml.etree import ElementTree as ET

from fastapi import HTTPException, UploadFile
from openai import APIError, OpenAI

from ..config import Settings
from .openai_payload import AttachmentMetadata, OpenAIMessageBuilder
from .prompt_store import PromptStore


@dataclass
class BufferedUpload:
    name: str
    content: bytes
    content_type: str | None


@dataclass
class GeneratedCsv:
    filename: str
    content: bytes
    csv_text: str


@dataclass
class UploadContext:
    upload: BufferedUpload
    metadata: Dict[str, Any] | None


@dataclass
class PromptContextPreview:
    descriptor: str
    doc_id: str | None

logger = logging.getLogger(__name__)


class AIGenerationService:
    def __init__(
        self,
        settings: Settings,
        prompt_store: PromptStore | None = None,
    ):
        self._settings = settings
        self._prompt_store = prompt_store or PromptStore(settings.prompt_store_path)
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            api_key = self._settings.openai_api_key
            if not api_key:
                raise HTTPException(status_code=500, detail="OpenAI API 키가 설정되어 있지 않습니다.")
            self._client = OpenAI(api_key=api_key)
        return self._client

    @staticmethod
    def _descriptor_from_context(context: UploadContext) -> tuple[str, str | None]:
        metadata = context.metadata or {}
        role = str(metadata.get("role") or "").strip()
        label = str(
            metadata.get("label") or metadata.get("description") or ""
        ).strip()

        extension = AIGenerationService._extension(context.upload)

        if role == "additional":
            base_label = label or "추가 문서"
            descriptor = f"추가 문서: {base_label}"
        elif label:
            descriptor = label
        else:
            descriptor = context.upload.name

        if extension:
            descriptor = f"{descriptor} ({extension})"

        doc_id = (
            str(metadata.get("id")) if role == "required" and metadata.get("id") else None
        )
        return descriptor, doc_id

    @staticmethod
    def _extension(upload: BufferedUpload) -> str:
        extension = os.path.splitext(upload.name)[1].lstrip(".")
        if extension:
            extension = extension.upper()
        elif upload.content_type:
            subtype = upload.content_type.split("/")[-1]
            extension = subtype.upper()
        mapping = {"JPEG": "JPG"}
        return mapping.get(extension, extension)

    @staticmethod
    def _attachment_kind(upload: BufferedUpload) -> Literal["file", "image"]:
        content_type = (upload.content_type or "").split(";")[0].strip().lower()
        if content_type.startswith("image/"):
            return "image"

        extension = os.path.splitext(upload.name)[1].lower()
        if extension in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".webp",
            ".tiff",
            ".tif",
            ".heic",
        }:
            return "image"

        return "file"

    @staticmethod
    def _closing_note(menu_id: str, contexts: List[PromptContextPreview]) -> str | None:
        if not contexts:
            return None

        def describe(preferred_ids: List[str]) -> str:
            ordered: List[str] = []
            for doc_id in preferred_ids:
                match = next(
                    (context.descriptor for context in contexts if context.doc_id == doc_id),
                    None,
                )
                if match:
                    ordered.append(match)
            if len(ordered) == len(preferred_ids):
                return ", ".join(ordered)
            return ", ".join(context.descriptor for context in contexts)

        if menu_id == "feature-list":
            description = describe(["user-manual", "configuration", "vendor-feature-list"])
            return (
                f"위 자료는 {description}입니다. 이 자료를 활용하여 기능리스트를 작성해 주세요."
            )

        if menu_id == "testcase-generation":
            description = describe(["user-manual", "configuration", "vendor-feature-list"])
            return (
                f"위 자료는 {description}입니다. 이 자료를 바탕으로 테스트케이스를 작성해 주세요."
            )

        return None

    @staticmethod
    def _build_context_previews(
        contexts: Iterable[UploadContext],
    ) -> List[PromptContextPreview]:
        previews: List[PromptContextPreview] = []
        for context in contexts:
            descriptor, doc_id = AIGenerationService._descriptor_from_context(context)
            cleaned = descriptor.strip() or context.upload.name
            previews.append(PromptContextPreview(descriptor=cleaned, doc_id=doc_id))
        return previews

    async def _upload_openai_file(self, client: OpenAI, context: UploadContext) -> str:
        upload = context.upload
        stream = io.BytesIO(upload.content)
        try:
            created = await asyncio.to_thread(
                client.files.create,
                file=(upload.name, stream),
                purpose="assistants",
            )
        except APIError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"OpenAI 파일 업로드 중 오류가 발생했습니다: {exc}",
            ) from exc
        except Exception as exc:  # pragma: no cover - 안전망
            raise HTTPException(
                status_code=502,
                detail="OpenAI 파일 업로드 중 예기치 않은 오류가 발생했습니다.",
            ) from exc

        file_id = getattr(created, "id", None)
        if not file_id and hasattr(created, "get"):
            try:
                file_id = created.get("id")  # type: ignore[call-arg]
            except Exception:  # pragma: no cover - dict-like guard
                file_id = None

        if not isinstance(file_id, str) or not file_id:
            raise HTTPException(
                status_code=502,
                detail="OpenAI 파일 업로드 응답에 file_id가 없습니다.",
            )

        return file_id

    async def _cleanup_openai_files(
        self, client: OpenAI, file_ids: Iterable[str]
    ) -> None:
        for file_id in file_ids:
            try:
                await asyncio.to_thread(client.files.delete, file_id=file_id)
            except Exception as exc:  # pragma: no cover - 로그 목적
                logger.warning(
                    "Failed to delete temporary OpenAI file",
                    extra={"file_id": file_id, "error": str(exc)},
                )

    @staticmethod
    def _sanitize_csv(text: str) -> str:
        cleaned = text.strip()
        fence_match = re.search(r"```(?:csv)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        return cleaned

    async def generate_csv(
        self,
        project_id: str,
        menu_id: str,
        uploads: List[UploadFile],
        metadata: List[Dict[str, Any]] | None = None,
    ) -> GeneratedCsv:
        prompt = self._prompt_store.get_prompt(menu_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="지원하지 않는 생성 메뉴입니다.")

        if not uploads:
            raise HTTPException(status_code=422, detail="업로드된 자료가 없습니다. 파일을 추가해 주세요.")

        buffered: List[BufferedUpload] = []
        for upload in uploads:
            try:
                data = await upload.read()
                name = upload.filename or "업로드된_파일"
                buffered.append(
                    BufferedUpload(
                        name=name,
                        content=data,
                        content_type=upload.content_type,
                    )
                )
            finally:
                await upload.close()

        contexts: List[UploadContext] = []
        metadata = metadata or []
        for index, upload in enumerate(buffered):
            entry = metadata[index] if index < len(metadata) else None
            contexts.append(UploadContext(upload=upload, metadata=entry))

        contexts.extend(self._builtin_attachment_contexts(menu_id))

        client = self._get_client()
        cleanup_file_ids: List[str] = []
        uploaded_attachments: List[AttachmentMetadata] = []

        try:
            context_previews = self._build_context_previews(contexts)
            closing_note = self._closing_note(menu_id, context_previews)

            descriptor_lines = [
                f"{index}. {preview.descriptor}"
                for index, preview in enumerate(context_previews, start=1)
                if preview.descriptor.strip()
            ]
            descriptor_section = "\n".join(descriptor_lines)

            for context in contexts:
                kind = self._attachment_kind(context.upload)
                if kind == "image":
                    image_url = self._image_data_url(context.upload)
                    uploaded_attachments.append(
                        {
                            "kind": "image",
                            "image_url": image_url,
                        }
                    )
                    continue

                file_id = await self._upload_openai_file(client, context)
                uploaded_attachments.append(
                    {"file_id": file_id, "kind": kind}
                )
                metadata = context.metadata or {}
                if not metadata.get("builtin"):
                    cleanup_file_ids.append(file_id)

            user_prompt_parts = [
                prompt["instruction"],
                (
                    "다음 첨부 파일을 참고하여 요구사항을 분석하고 지침에 맞는 CSV를 작성하세요."
                ),
                "각 파일은 업로드된 순서대로 첨부되어 있습니다.",
            ]
            if descriptor_section:
                user_prompt_parts.append("첨부 파일 목록:")
                user_prompt_parts.append(descriptor_section)
            if closing_note:
                user_prompt_parts.append(closing_note)
            user_prompt_parts.append("CSV 이외의 다른 형식이나 설명 문장은 포함하지 마세요.")

            user_prompt = "\n\n".join(part for part in user_prompt_parts if part.strip())

            messages = [
                OpenAIMessageBuilder.text_message("system", prompt["system"]),
                OpenAIMessageBuilder.text_message(
                    "user",
                    user_prompt,
                    attachments=uploaded_attachments,
                ),
            ]

            normalized_messages = OpenAIMessageBuilder.normalize_messages(messages)

            logger.info(
                "AI generation prompt assembled",
                extra={
                    "project_id": project_id,
                    "menu_id": menu_id,
                    "system_prompt": prompt["system"],
                    "user_prompt": user_prompt,
                },
            )

            try:
                response = await asyncio.to_thread(
                    client.responses.create,
                    model=self._settings.openai_model,
                    input=normalized_messages,
                    temperature=0.2,
                    max_output_tokens=1500,
                )
            except APIError as exc:
                raise HTTPException(status_code=502, detail=f"OpenAI 호출 중 오류가 발생했습니다: {exc}") from exc
            except Exception as exc:  # pragma: no cover - 안전망
                raise HTTPException(status_code=502, detail="OpenAI 응답을 가져오는 중 예기치 않은 오류가 발생했습니다.") from exc

            csv_text = getattr(response, "output_text", None)
            if not csv_text:
                raise HTTPException(status_code=502, detail="OpenAI 응답에서 CSV를 찾을 수 없습니다.")

            sanitized = self._sanitize_csv(csv_text)
            if not sanitized:
                raise HTTPException(status_code=502, detail="생성된 CSV 내용이 비어 있습니다.")

            encoded = sanitized.encode("utf-8-sig")
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            safe_project = re.sub(r"[^A-Za-z0-9_-]+", "_", project_id)
            filename = f"{safe_project}_{menu_id}_{timestamp}.csv"

            return GeneratedCsv(filename=filename, content=encoded, csv_text=sanitized)
        finally:
            if cleanup_file_ids:
                await self._cleanup_openai_files(client, cleanup_file_ids)

    @staticmethod
    def _image_data_url(upload: BufferedUpload) -> str:
        media_type = (upload.content_type or "").split(";")[0].strip()
        if not media_type:
            guessed, _ = mimetypes.guess_type(upload.name)
            if guessed:
                media_type = guessed

        if not media_type:
            media_type = "application/octet-stream"

        encoded = base64.b64encode(upload.content).decode("ascii")
        return f"data:{media_type};base64,{encoded}"

    @staticmethod
    def _builtin_attachment_contexts(menu_id: str) -> List[UploadContext]:
        if menu_id != "feature-list":
            return []

        template_path = (
            Path(__file__).resolve().parents[2]
            / "template"
            / "가.계획"
            / "GS-B-XX-XXXX 기능리스트 v1.0.xlsx"
        )

        upload = AIGenerationService._load_feature_template_pdf(menu_id, template_path)

        metadata: Dict[str, Any] = {
            "role": "additional",
            "label": "기능리스트 예제 양식",
            "builtin": True,
        }

        return [UploadContext(upload=upload, metadata=metadata)]

    @staticmethod
    def _load_feature_template_pdf(menu_id: str, template_path: Path) -> BufferedUpload:
        try:
            content = template_path.read_bytes()
        except FileNotFoundError as exc:
            logger.error(
                "기능리스트 예제 파일을 찾을 수 없습니다.",
                extra={"menu_id": menu_id, "path": str(template_path)},
            )
            raise HTTPException(
                status_code=500,
                detail="기능리스트 예제 파일을 찾을 수 없습니다.",
            ) from exc
        except OSError as exc:
            logger.error(
                "기능리스트 예제 파일을 읽는 중 오류가 발생했습니다.",
                extra={"menu_id": menu_id, "path": str(template_path), "error": str(exc)},
            )
            raise HTTPException(
                status_code=500,
                detail="기능리스트 예제 파일을 읽는 중 오류가 발생했습니다.",
            ) from exc

        try:
            rows = AIGenerationService._parse_xlsx_rows(content)
        except ValueError as exc:
            logger.error(
                "기능리스트 예제 파일을 PDF로 변환하는 중 오류가 발생했습니다.",
                extra={
                    "menu_id": menu_id,
                    "path": str(template_path),
                    "error": str(exc),
                },
            )
            raise HTTPException(
                status_code=500,
                detail="기능리스트 예제 파일을 PDF로 변환하는 중 오류가 발생했습니다.",
            ) from exc

        pdf_bytes = AIGenerationService._rows_to_pdf(rows)

        return BufferedUpload(
            name=template_path.with_suffix(".pdf").name,
            content=pdf_bytes,
            content_type="application/pdf",
        )

    @staticmethod
    def _rows_to_pdf(rows: List[List[str]]) -> bytes:
        lines: List[str] = []
        for row in rows:
            if row:
                line = ", ".join(cell.strip() for cell in row)
            else:
                line = ""
            lines.append(line)

        if not lines:
            lines.append("")

        def _escape(text: str) -> str:
            encoded = ("\ufeff" + text).encode("utf-16-be")
            return "".join(f"\\{byte:03o}" for byte in encoded)

        content_lines = [
            "BT",
            "/F1 11 Tf",
            "1 0 0 1 72 770 Tm",
            "14 TL",
        ]
        for line in lines:
            escaped = _escape(line)
            content_lines.append(f"({escaped}) Tj")
            content_lines.append("T*")
        content_lines.append("ET")

        content_stream = "\n".join(content_lines).encode("utf-8")

        objects: List[bytes] = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 6 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
            b"<< /Type /Font /Subtype /Type0 /BaseFont /HYGoThic-Medium /Encoding /UniKS-UCS2-H /DescendantFonts [5 0 R] >>",
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HYGoThic-Medium /CIDSystemInfo << /Registry (Adobe) /Ordering (Korea1) /Supplement 0 >> /DW 1000 >>",
            b"<< /Length %d >>\nstream\n" % len(content_stream)
            + content_stream
            + b"\nendstream",
        ]

        buffer = io.BytesIO()
        buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: List[int] = []
        for index, obj in enumerate(objects, start=1):
            offsets.append(buffer.tell())
            buffer.write(f"{index} 0 obj\n".encode("ascii"))
            buffer.write(obj)
            buffer.write(b"\nendobj\n")

        xref_offset = buffer.tell()
        total_objects = len(objects) + 1
        buffer.write(f"xref\n0 {total_objects}\n".encode("ascii"))
        buffer.write(b"0000000000 65535 f \n")
        for offset in offsets:
            buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        buffer.write(
            b"trailer\n<< /Size "
            + str(total_objects).encode("ascii")
            + b" /Root 1 0 R >>\nstartxref\n"
            + str(xref_offset).encode("ascii")
            + b"\n%%EOF\n"
        )

        return buffer.getvalue()

    @staticmethod
    def _parse_xlsx_rows(content: bytes) -> List[List[str]]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise ValueError("잘못된 XLSX 형식입니다.") from exc

        with archive:
            shared_strings = AIGenerationService._read_shared_strings(archive)
            try:
                with archive.open("xl/worksheets/sheet1.xml") as sheet_file:
                    tree = ET.parse(sheet_file)
            except KeyError as exc:
                raise ValueError("기본 시트를 찾을 수 없습니다.") from exc
            except ET.ParseError as exc:
                raise ValueError("시트 XML을 해석할 수 없습니다.") from exc

            namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            root = tree.getroot()
            sheet_data = root.find("main:sheetData", namespace)
            if sheet_data is None:
                return []

            rows: List[List[str]] = []
            for row_elem in sheet_data.findall("main:row", namespace):
                row_values: List[str] = []
                for cell_elem in row_elem.findall("main:c", namespace):
                    column_index = AIGenerationService._column_index_from_ref(cell_elem.get("r"))
                    value = AIGenerationService._extract_cell_value(cell_elem, shared_strings, namespace)
                    if column_index is None:
                        column_index = len(row_values)
                    while len(row_values) <= column_index:
                        row_values.append("")
                    row_values[column_index] = value
                rows.append(row_values)

            return rows

    @staticmethod
    def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
        try:
            with archive.open("xl/sharedStrings.xml") as handle:
                tree = ET.parse(handle)
        except KeyError:
            return []
        except ET.ParseError as exc:
            raise ValueError("공유 문자열 XML을 해석할 수 없습니다.") from exc

        namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings: List[str] = []
        root = tree.getroot()
        for si in root.findall("main:si", namespace):
            text_parts = [node.text or "" for node in si.findall(".//main:t", namespace)]
            strings.append("".join(text_parts))
        return strings

    @staticmethod
    def _column_index_from_ref(ref: str | None) -> int | None:
        if not ref:
            return None
        match = re.match(r"([A-Z]+)", ref)
        if not match:
            return None
        letters = match.group(1)
        index = 0
        for letter in letters:
            index = index * 26 + (ord(letter) - ord("A") + 1)
        return index - 1

    @staticmethod
    def _extract_cell_value(
        cell_elem: ET.Element,
        shared_strings: List[str],
        namespace: Dict[str, str],
    ) -> str:
        cell_type = cell_elem.get("t")
        if cell_type == "s":
            index_text = cell_elem.findtext("main:v", default="", namespaces=namespace)
            try:
                shared_index = int(index_text)
            except (TypeError, ValueError):
                return ""
            if 0 <= shared_index < len(shared_strings):
                return shared_strings[shared_index]
            return ""

        if cell_type == "inlineStr":
            text_nodes = cell_elem.findall(".//main:t", namespace)
            return "".join(node.text or "" for node in text_nodes)

        value = cell_elem.findtext("main:v", default="", namespaces=namespace)
        if value:
            return value

        text_nodes = cell_elem.findall(".//main:t", namespace)
        if text_nodes:
            return "".join(node.text or "" for node in text_nodes)

        return ""
