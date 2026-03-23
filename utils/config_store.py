"""Simple JSON-backed storage for lightweight UI preferences."""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict


APP_NAME = "YTGrab"


def _config_dir() -> str:
    candidates = []

    appdata_dir = os.environ.get("APPDATA")
    if appdata_dir:
        candidates.append(os.path.join(appdata_dir, APP_NAME))

    candidates.append(os.path.join(os.path.expanduser("~"), ".config", APP_NAME))
    candidates.append(os.path.join(os.getcwd(), ".ytgrab"))
    candidates.append(os.path.join(tempfile.gettempdir(), APP_NAME))

    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            probe_path = os.path.join(candidate, ".write-test")
            with open(probe_path, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(probe_path)
            return candidate
        except Exception:
            continue

    return os.getcwd()


def get_app_data_dir() -> str:
    """Return writable runtime data directory for this app."""
    return _config_dir()


def _config_path(filename: str = "ui_state.json") -> str:
    return os.path.join(_config_dir(), filename)


def load_ui_state(filename: str = "ui_state.json") -> Dict[str, Any]:
    """Return persisted UI state, or an empty dictionary on failure."""
    path = _config_path(filename)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_ui_state(payload: Dict[str, Any], filename: str = "ui_state.json") -> None:
    """Persist UI state atomically when possible."""
    if not isinstance(payload, dict):
        return

    path = _config_path(filename)
    temp_path = f"{path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temp_path, path)
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
