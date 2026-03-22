"""Cache remote thumbnail images locally for UI previews."""
from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from io import BytesIO
from typing import Iterable, Optional

from PIL import Image


class ThumbnailCacheManager:
    """Downloads and stores remote thumbnails in a local cache folder."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = os.path.abspath(base_dir or os.getcwd())
        self.cache_dir = self._resolve_cache_dir()

    def _resolve_cache_dir(self) -> str:
        candidates = [
            os.path.join(self.base_dir, "cache", "thumbnails"),
            os.path.join(os.getcwd(), "cache", "thumbnails"),
            os.path.join(tempfile.gettempdir(), "YTGrab", "cache", "thumbnails"),
        ]

        for candidate in candidates:
            try:
                os.makedirs(candidate, exist_ok=True)
                return candidate
            except Exception:
                continue

        return os.getcwd()

    def _path_for_url(self, url: str) -> str:
        digest = hashlib.sha1((url or "").encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.png")

    def get_cached_path(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        path = self._path_for_url(url)
        return path if os.path.exists(path) else None

    def ensure_cached(self, url: Optional[str]) -> Optional[str]:
        if not url:
            return None

        cached = self.get_cached_path(url)
        if cached:
            return cached

        target_path = self._path_for_url(url)
        temp_path = f"{target_path}.tmp"

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read()

            with Image.open(BytesIO(payload)) as raw_image:
                image = raw_image.convert("RGB")
                image.thumbnail((640, 360), Image.Resampling.LANCZOS)
                image.save(temp_path, format="PNG", optimize=True)

            os.replace(temp_path, target_path)
            return target_path
        except Exception:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            return None

    def remove_path(self, path: Optional[str]) -> None:
        if not path:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def remove_for_items(self, items: Iterable[object]) -> None:
        seen = set()
        for item in items:
            path = getattr(item, "cached_thumbnail_path", None)
            if path and path not in seen:
                self.remove_path(path)
                seen.add(path)
