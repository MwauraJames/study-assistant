from __future__ import annotations

import re
from pathlib import Path

_NON_SLUG = re.compile(r"[^a-z0-9]+")
_CITATION = re.compile(r"【.*?】")


def slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = _NON_SLUG.sub("-", slug)
    return slug.strip("-")


def clean_answer(text: str) -> str:
    if not text:
        return ""
    cleaned = _CITATION.sub("", text)
    return cleaned.strip()


def safe_filename(name: str | None) -> str:
    if not name:
        return "untitled"
    return Path(name).name


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "—"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
