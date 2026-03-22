"""Helpers for resolving media preview metadata."""
from __future__ import annotations

from typing import Any, Optional


def _thumbnail_from_info(info: Any) -> Optional[str]:
    if not isinstance(info, dict):
        return None

    thumbnail = info.get("thumbnail")
    if isinstance(thumbnail, str) and thumbnail.strip():
        return thumbnail.strip()

    thumbnails = info.get("thumbnails")
    if isinstance(thumbnails, list):
        for candidate in reversed(thumbnails):
            if not isinstance(candidate, dict):
                continue
            url = candidate.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()

    return None


def resolve_thumbnail_url(info: Any) -> Optional[str]:
    """Prefer the first playlist entry thumbnail before the playlist thumbnail."""
    if not isinstance(info, dict):
        return None

    entries = info.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            first_entry_thumbnail = _thumbnail_from_info(entry)
            if first_entry_thumbnail:
                return first_entry_thumbnail
            break

    return _thumbnail_from_info(info)
