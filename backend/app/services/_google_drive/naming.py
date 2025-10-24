"""Naming utilities for Google Drive resources."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Sequence, Tuple


def normalize_drive_text(value: str) -> str:
    """Normalize unicode text and collapse whitespace for comparisons."""

    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = normalized.replace("\xa0", " ")
    normalized = normalized.strip().lower()
    return re.sub(r"\s+", " ", normalized)


def squash_drive_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[\s._\-()]+", "", value)


def strip_drive_extension(value: str) -> str:
    if "." in value:
        return value.rsplit(".", 1)[0]
    return value


def strip_drive_version_suffix(value: str) -> str:
    return re.sub(r"v\s*\d+(?:[._\-]\d+)*$", "", value).strip()


def drive_name_variants(value: str) -> Tuple[str, ...]:
    normalized = normalize_drive_text(value)
    if not normalized:
        return tuple()

    variants = {normalized}

    squashed = squash_drive_text(normalized)
    if squashed:
        variants.add(squashed)

    stem = strip_drive_extension(normalized)
    if stem and stem != normalized:
        variants.add(stem)
        squashed_stem = squash_drive_text(stem)
        if squashed_stem:
            variants.add(squashed_stem)

    versionless = strip_drive_version_suffix(stem)
    if versionless and versionless not in variants:
        variants.add(versionless)
        squashed_versionless = squash_drive_text(versionless)
        if squashed_versionless:
            variants.add(squashed_versionless)

    return tuple(variant for variant in variants if len(variant) >= 2)


def drive_name_matches(value: str, expected: str) -> bool:
    actual_tokens = set(drive_name_variants(value))
    expected_tokens = set(drive_name_variants(expected))
    if not actual_tokens or not expected_tokens:
        return False
    return bool(actual_tokens & expected_tokens)


def drive_suffix_matches(name: str, suffix: str) -> bool:
    if not suffix:
        return False
    suffix_tokens = set(drive_name_variants(suffix))
    if not suffix_tokens:
        return False

    name_tokens = set(drive_name_variants(name))
    if not name_tokens:
        return False

    for token in name_tokens:
        for suffix_token in suffix_tokens:
            if suffix_token and (token.endswith(suffix_token) or suffix_token in token):
                return True
    return False


def looks_like_header_row(values: Sequence[Any], expected: Sequence[str]) -> bool:
    if not values:
        return False

    normalized_values = [
        normalize_drive_text(str(value)) if value is not None else ""
        for value in values
    ]
    squashed_values = [squash_drive_text(value) for value in normalized_values]
    normalized_expected = [normalize_drive_text(name) for name in expected]
    squashed_expected = [squash_drive_text(name) for name in normalized_expected]

    matches = 0
    for expected_value, expected_squashed in zip(normalized_expected, squashed_expected):
        if not expected_value and not expected_squashed:
            continue

        for actual_value, actual_squashed in zip(normalized_values, squashed_values):
            if not actual_value and not actual_squashed:
                continue

            normalized_match = (
                bool(expected_value)
                and bool(actual_value)
                and (
                    actual_value == expected_value
                    or expected_value in actual_value
                    or actual_value in expected_value
                )
            )
            squashed_match = (
                bool(expected_squashed)
                and bool(actual_squashed)
                and expected_squashed in actual_squashed
            )

            if normalized_match or squashed_match:
                matches += 1
                break

    if not matches:
        return False

    threshold = max(1, len(normalized_expected) - 1)
    return matches >= threshold


def any_name_matches(names: Iterable[str], expected: str) -> bool:
    return any(drive_name_matches(name, expected) for name in names)

