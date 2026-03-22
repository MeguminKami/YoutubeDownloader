"""Persistence helpers for download history."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, Optional

from core.models import DownloadItem
from utils.config_store import load_ui_state, save_ui_state


HISTORY_STATE_FILE = "history.json"


def _serialize_history_item(item: DownloadItem) -> dict:
    payload = dict(item.__dict__)

    queued_at = payload.get("queued_at")
    finished_at = payload.get("finished_at")

    payload["queued_at"] = queued_at.isoformat() if isinstance(queued_at, datetime) else None
    payload["finished_at"] = finished_at.isoformat() if isinstance(finished_at, datetime) else None
    return payload


def _deserialize_history_item(payload: dict) -> Optional[DownloadItem]:
    if not isinstance(payload, dict):
        return None

    valid_keys = set(DownloadItem.__dataclass_fields__.keys())
    filtered = {key: value for key, value in payload.items() if key in valid_keys}

    if not filtered.get("url"):
        return None

    for key in ("queued_at", "finished_at"):
        raw_value = filtered.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            try:
                filtered[key] = datetime.fromisoformat(raw_value)
            except Exception:
                filtered[key] = None
        elif not isinstance(raw_value, datetime):
            filtered[key] = None

    cached_path = filtered.get("cached_thumbnail_path")
    if cached_path and not os.path.exists(cached_path):
        filtered["cached_thumbnail_path"] = None

    try:
        return DownloadItem(**filtered)
    except Exception:
        return None


def load_history_items() -> list[DownloadItem]:
    state = load_ui_state(HISTORY_STATE_FILE)
    raw_items = state.get("items", []) if isinstance(state, dict) else []
    return [item for item in (_deserialize_history_item(raw_item) for raw_item in raw_items) if item is not None]


def save_history_items(items: Iterable[DownloadItem]) -> None:
    payload = {"items": [_serialize_history_item(item) for item in items]}
    save_ui_state(payload, HISTORY_STATE_FILE)
