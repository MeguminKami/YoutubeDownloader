"""
YouTube Authentication via cookies.txt

This module manages a local cookies.txt file for YouTube authentication.
"""
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

from utils.config_store import get_app_data_dir


def _default_app_dir() -> str:
    """Return persistent runtime directory for config/auth files."""
    return get_app_data_dir()


def _legacy_cookie_candidates() -> list[str]:
    candidates: list[str] = []

    # Historical dev path fallback.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(project_root, "cookies.txt"))

    # Current working directory fallback.
    candidates.append(os.path.join(os.getcwd(), "cookies.txt"))

    # Frozen executable directory fallback.
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "cookies.txt"))

    unique: list[str] = []
    for path in candidates:
        normalized = os.path.abspath(path)
        if normalized not in unique:
            unique.append(normalized)
    return unique


AUTH_COOKIE_NAMES = {
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "LOGIN_INFO",
    "SIDCC",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "__Secure-1PSIDCC",
    "__Secure-3PSIDCC",
}

AUTH_COOKIE_DOMAINS = ("youtube.com", "google.com")


class CookieManager:
    """Manages local cookies.txt file for yt-dlp authentication."""

    def __init__(self, app_dir: Optional[str] = None):
        """
        Initialize cookie manager.

        Args:
            app_dir: Application directory. Defaults to script directory.
        """
        if app_dir:
            self.app_dir = app_dir
        else:
            self.app_dir = _default_app_dir()

        os.makedirs(self.app_dir, exist_ok=True)
        self.cookie_file = os.path.join(self.app_dir, 'cookies.txt')
        self._migrate_legacy_cookie_file()

    def _migrate_legacy_cookie_file(self) -> None:
        if os.path.exists(self.cookie_file):
            return

        for legacy_path in _legacy_cookie_candidates():
            if legacy_path == os.path.abspath(self.cookie_file):
                continue
            if not os.path.isfile(legacy_path):
                continue

            try:
                shutil.copy2(legacy_path, self.cookie_file)
                return
            except Exception:
                continue

    def has_valid_cookies(self) -> bool:
        """Check if valid cookies.txt file exists."""
        return self.get_cookie_status()["authenticated"]

    def _read_cookie_rows(self) -> list[dict]:
        rows = []
        with open(self.cookie_file, "r", encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split("\t")
                if len(parts) < 7:
                    continue

                domain, include_subdomains, path, secure, expires, name, value = parts[:7]
                try:
                    expires_at = int(expires)
                except Exception:
                    expires_at = 0

                rows.append({
                    "domain": domain.lower(),
                    "include_subdomains": include_subdomains,
                    "path": path,
                    "secure": secure,
                    "expires": expires_at,
                    "name": name,
                    "value": value,
                })
        return rows

    def get_cookie_file_path(self) -> Optional[str]:
        """Get path to cookies.txt if the file exists."""
        if os.path.exists(self.cookie_file):
            return self.cookie_file
        return None

    def get_cookie_status(self) -> dict:
        """Get current authentication status."""
        status = {
            "authenticated": False,
            "cookie_file": self.cookie_file if os.path.exists(self.cookie_file) else None,
            "reason": "missing_file",
            "has_cookie_file": os.path.exists(self.cookie_file),
            "has_youtube_cookies": False,
            "valid_auth_count": 0,
            "expired_auth_count": 0,
            "session_auth_count": 0,
        }

        if not status["has_cookie_file"]:
            return status

        try:
            rows = self._read_cookie_rows()
        except Exception:
            status["reason"] = "unreadable_file"
            return status

        youtube_rows = [
            row for row in rows
            if any(domain in row["domain"] for domain in AUTH_COOKIE_DOMAINS)
        ]
        status["has_youtube_cookies"] = bool(youtube_rows)

        auth_rows = [row for row in youtube_rows if row["name"] in AUTH_COOKIE_NAMES]
        now = int(time.time())

        for row in auth_rows:
            expires_at = row["expires"]
            if expires_at == 0:
                status["session_auth_count"] += 1
            elif expires_at > now:
                status["valid_auth_count"] += 1
            else:
                status["expired_auth_count"] += 1

        status["authenticated"] = (status["valid_auth_count"] + status["session_auth_count"]) > 0

        if status["authenticated"]:
            status["reason"] = "ok"
        elif not youtube_rows:
            status["reason"] = "missing_youtube_cookies"
        elif status["expired_auth_count"] > 0:
            status["reason"] = "expired_auth_cookies"
        else:
            status["reason"] = "missing_auth_cookies"

        return status

    def get_ydl_opts(self) -> dict:
        """
        Get yt-dlp options for authenticated requests.

        Returns:
            Dictionary of yt-dlp options including auth settings
        """
        opts = {}

        cookie_file = self.get_cookie_file_path()
        if cookie_file:
            opts['cookiefile'] = cookie_file

        return opts

    def validate_cookies_with_ytdlp(self) -> bool:
        """
        Validate cookies by making a test yt-dlp request.

        Returns:
            True if cookies work, False otherwise
        """
        if not os.path.exists(self.cookie_file):
            return False

        try:
            # Make a simple test request to YouTube
            cmd = [
                'yt-dlp',
                '--cookies', self.cookie_file,
                '--skip-download',
                '--quiet',
                '--no-warnings',
                'https://www.youtube.com/watch?v=dQw4w9WgXcQ'  # Short test video
            ]

            # Prefer bundled/runtime-resolved yt-dlp in packaged builds.
            from core.downloader import resolve_runtime_tool
            resolved = resolve_runtime_tool('yt-dlp', allow_python_module_fallback=True)
            if resolved:
                cmd = resolved + cmd[1:]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            # If the command succeeds without errors, cookies are valid
            return result.returncode == 0
        except Exception:
            return False


