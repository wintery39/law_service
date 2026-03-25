from __future__ import annotations

import hashlib
import re
from datetime import date


TOKEN_RE = re.compile(r"[^a-zA-Z0-9가-힣._/-]+")


def normalize_token(value: str | int | None, fallback: str = "unknown") -> str:
    text = fallback if value in (None, "") else str(value).strip()
    text = TOKEN_RE.sub("_", text)
    return text.strip("_") or fallback


def format_date_token(value: date | None, fallback: str = "na") -> str:
    return fallback if value is None else value.strftime("%Y%m%d")


def build_version_key(
    promulgated_at: date | None,
    effective_at: date | None,
    promulgation_number: str | None,
    history_code: str | None,
) -> str:
    return "-".join(
        [
            format_date_token(promulgated_at),
            format_date_token(effective_at),
            normalize_token(promulgation_number, fallback="no"),
            normalize_token(history_code, fallback="cur"),
        ]
    )


def build_internal_id(
    jurisdiction: str,
    official_law_id: str,
    version_key: str,
    unit_path: str,
) -> str:
    return ":".join(
        [
            normalize_token(jurisdiction),
            normalize_token(official_law_id),
            normalize_token(version_key),
            normalize_token(unit_path),
        ]
    )


def build_law_id(jurisdiction: str, official_law_id: str) -> str:
    return build_internal_id(jurisdiction, official_law_id, "law", "root")


def build_version_id(jurisdiction: str, official_law_id: str, version_key: str) -> str:
    return build_internal_id(jurisdiction, official_law_id, version_key, "version")


def build_reference_id(
    jurisdiction: str,
    official_law_id: str,
    version_key: str,
    source_unit_path: str,
    raw_text: str,
) -> str:
    digest = hashlib.sha1(f"{source_unit_path}|{raw_text}".encode("utf-8")).hexdigest()[:12]
    return build_internal_id(
        jurisdiction,
        official_law_id,
        version_key,
        f"ref/{normalize_token(source_unit_path)}/{digest}",
    )
