from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Sequence, Set


class DriveFileType(str, Enum):
    pdf = "pdf"
    txt = "txt"
    jpg = "jpg"
    csv = "csv"
    html = "html"


@dataclass(frozen=True)
class DriveFileTypeDefinition:
    extensions: Set[str]
    mime_types: Set[str]


FILE_TYPE_DEFINITIONS = {
    DriveFileType.pdf: DriveFileTypeDefinition(
        extensions={"pdf"},
        mime_types={"application/pdf"},
    ),
    DriveFileType.txt: DriveFileTypeDefinition(
        extensions={"txt"},
        mime_types={"text/plain"},
    ),
    DriveFileType.jpg: DriveFileTypeDefinition(
        extensions={"jpg", "jpeg"},
        mime_types={"image/jpeg"},
    ),
    DriveFileType.csv: DriveFileTypeDefinition(
        extensions={"csv"},
        mime_types={"text/csv", "application/vnd.ms-excel"},
    ),
    DriveFileType.html: DriveFileTypeDefinition(
        extensions={"html", "htm"},
        mime_types={"text/html"},
    ),
}


def normalise_file_types(values: Iterable[str] | None) -> List[DriveFileType]:
    if not values:
        return [DriveFileType.pdf]

    seen: Set[DriveFileType] = set()
    normalised: List[DriveFileType] = []
    for value in values:
        try:
            file_type = DriveFileType(value.lower())
        except ValueError:
            continue
        if file_type in seen:
            continue
        seen.add(file_type)
        normalised.append(file_type)
    return normalised or [DriveFileType.pdf]


def is_allowed_filename(filename: str, allowed_types: Iterable[DriveFileType]) -> bool:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for file_type in allowed_types:
        definition = FILE_TYPE_DEFINITIONS[file_type]
        if extension in definition.extensions:
            return True
    return False


def infer_file_type(filename: str, allowed_types: Sequence[DriveFileType]) -> DriveFileType:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for file_type in allowed_types:
        definition = FILE_TYPE_DEFINITIONS[file_type]
        if extension in definition.extensions:
            return file_type
    return allowed_types[0]


def resolve_content_type(original: str | None, fallback: DriveFileType) -> str:
    if original:
        return original
    definition = FILE_TYPE_DEFINITIONS[fallback]
    return next(iter(definition.mime_types))
