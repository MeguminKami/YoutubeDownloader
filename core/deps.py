"""
Runtime dependency and frozen-path helpers for YoutubeGrab.

This module centralizes:
- bundled resource lookup for PyInstaller one-folder bundles
- bundled/runtime tool resolution for yt-dlp, ffmpeg, ffprobe, and deno
- development fallbacks for source-mode execution
- runtime diagnostics used by self-checks and troubleshooting
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional


APP_NAME = "YoutubeGrab"
RUNTIME_DIR_NAME = "runtime"
RUNTIME_BIN_RELATIVE = Path(RUNTIME_DIR_NAME) / "bin"
RUNTIME_MANIFEST_RELATIVE = Path(RUNTIME_DIR_NAME) / "manifest.json"
RELEASE_REQUIRED_TOOLS = ("yt-dlp", "ffmpeg", "ffprobe", "deno")
SOURCE_REQUIRED_TOOLS = ("yt-dlp",)

SUBPROCESS_TEXT_KWARGS = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
}


def is_frozen_runtime() -> bool:
    """Return True when running inside a PyInstaller-frozen application."""
    return bool(getattr(sys, "frozen", False))


def get_project_root() -> Path:
    """Return the repository root during source-mode execution."""
    return Path(__file__).resolve().parent.parent


def get_executable_path() -> Path:
    """Return the current executable or interpreter path."""
    return Path(sys.executable).resolve()


def get_executable_dir() -> Path:
    """Return the directory containing the current executable/interpreter."""
    return get_executable_path().parent


def _mac_bundle_dirs() -> list[Path]:
    if sys.platform != "darwin" or not is_frozen_runtime():
        return []

    executable_dir = get_executable_dir()
    contents_dir = executable_dir.parent
    return [
        executable_dir,
        contents_dir / "Frameworks",
        contents_dir / "Resources",
    ]


def _base_search_dirs() -> list[Path]:
    """
    Return candidate directories that may contain bundled resources/support files.

    PyInstaller one-folder bundles commonly place supporting files in `_internal`.
    macOS bundles may place them in `Contents/Frameworks` or `Contents/Resources`.
    """
    dirs: list[Path] = []

    def add(path: Optional[Path]) -> None:
        if not path:
            return
        resolved = path.resolve()
        if resolved not in dirs:
            dirs.append(resolved)

    if is_frozen_runtime():
        executable_dir = get_executable_dir()
        add(executable_dir)
        add(executable_dir / "_internal")

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            add(Path(meipass))

        for path in _mac_bundle_dirs():
            add(path)
            add(path / "_internal")
    else:
        project_root = get_project_root()
        add(project_root)
        add(project_root / ".runtime")

        runtime_override = os.environ.get("YTG_RUNTIME_DIR")
        if runtime_override:
            add(Path(runtime_override))

    return dirs


def get_resource_search_dirs() -> list[Path]:
    """Return directories that may contain packaged non-code resources."""
    return _base_search_dirs()


def get_runtime_bin_search_dirs() -> list[Path]:
    """Return directories that may contain bundled helper executables."""
    search_dirs: list[Path] = []

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved not in search_dirs:
            search_dirs.append(resolved)

    for base_dir in _base_search_dirs():
        add(base_dir / RUNTIME_BIN_RELATIVE)
        add(base_dir / "bin")
        add(base_dir)

    return search_dirs


def find_bundled_resource(*relative_parts: str) -> Optional[str]:
    """Return the path to a bundled resource, or None if it cannot be found."""
    relative_path = Path(*relative_parts)

    for base_dir in get_resource_search_dirs():
        candidate = base_dir / relative_path
        if candidate.is_file():
            return str(candidate)

    return None


def find_runtime_manifest_path() -> Optional[str]:
    """Return the path to the runtime manifest when present."""
    return find_bundled_resource(*RUNTIME_MANIFEST_RELATIVE.parts)


def get_runtime_manifest() -> Optional[dict[str, Any]]:
    """Load the runtime manifest if the packaged/downloaded tool bundle provides one."""
    manifest_path = find_runtime_manifest_path()
    if not manifest_path:
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _candidate_binary_names(tool_name: str) -> list[str]:
    if sys.platform == "win32":
        return [f"{tool_name}.exe", tool_name]
    return [tool_name]


def find_bundled_binary(tool_name: str) -> Optional[str]:
    """Return the path to a bundled runtime tool if it exists."""
    for search_dir in get_runtime_bin_search_dirs():
        for candidate_name in _candidate_binary_names(tool_name):
            candidate_path = search_dir / candidate_name
            if not candidate_path.is_file():
                continue

            if sys.platform != "win32" and not os.access(candidate_path, os.X_OK):
                continue

            return str(candidate_path)

    return None


def find_system_binary(tool_name: str) -> Optional[str]:
    """Return a tool from PATH if available."""
    return shutil.which(tool_name)


def resolve_runtime_tool(tool_name: str, allow_python_fallback: bool = False) -> Optional[list[str]]:
    """
    Resolve a tool into a subprocess-ready command list.

    Resolution order:
    1. bundled runtime tool inside the application
    2. system PATH
    3. `python -m yt_dlp` fallback for source-mode yt-dlp usage
    """
    bundled_binary = find_bundled_binary(tool_name)
    if bundled_binary:
        return [bundled_binary]

    path_binary = find_system_binary(tool_name)
    if path_binary:
        return [path_binary]

    if allow_python_fallback and tool_name == "yt-dlp" and not is_frozen_runtime():
        try:
            import yt_dlp  # noqa: F401
            return [sys.executable, "-m", "yt_dlp"]
        except ImportError:
            return None

    return None


def resolve_binary_path(tool_name: str) -> Optional[str]:
    """Resolve a tool into a single executable path."""
    command = resolve_runtime_tool(tool_name, allow_python_fallback=False)
    if command and len(command) == 1:
        return command[0]
    return None


def resolve_ffmpeg_binary() -> Optional[str]:
    return resolve_binary_path("ffmpeg")


def resolve_ffprobe_binary() -> Optional[str]:
    return resolve_binary_path("ffprobe")


def resolve_ytdlp_binary() -> Optional[str]:
    return resolve_binary_path("yt-dlp")


def resolve_deno_binary() -> Optional[str]:
    return resolve_binary_path("deno")


def build_yt_dlp_command(allow_python_fallback: bool = True) -> Optional[list[str]]:
    """Return the preferred yt-dlp command including bundled JS runtime wiring."""
    command = resolve_runtime_tool("yt-dlp", allow_python_fallback=allow_python_fallback)
    if not command:
        return None

    deno_binary = resolve_deno_binary()
    if deno_binary:
        return command + ["--js-runtimes", f"deno:{deno_binary}"]

    return command


def build_yt_dlp_python_options() -> dict[str, Any]:
    """Return yt-dlp Python API options that mirror the bundled subprocess behavior."""
    options: dict[str, Any] = {}
    deno_binary = resolve_deno_binary()
    if deno_binary:
        options["js_runtimes"] = {"deno": {"executable": deno_binary}}
    return options


def get_required_tools_for_runtime() -> tuple[str, ...]:
    """Return tools required for the current runtime mode."""
    if is_frozen_runtime():
        return RELEASE_REQUIRED_TOOLS
    return SOURCE_REQUIRED_TOOLS


def get_missing_bundled_tools() -> list[str]:
    """
    Return required bundled tools missing from a frozen release.

    Frozen builds should be self-contained across all supported platforms.
    """
    if not is_frozen_runtime():
        return []

    missing: list[str] = []
    for tool_name in RELEASE_REQUIRED_TOOLS:
        if not find_bundled_binary(tool_name):
            missing.append(tool_name)
    return missing


def get_missing_runtime_tools() -> list[str]:
    """Return required tools that cannot be resolved at runtime."""
    missing: list[str] = []

    for tool_name in get_required_tools_for_runtime():
        if tool_name == "yt-dlp":
            command = build_yt_dlp_command(allow_python_fallback=True)
        else:
            command = resolve_runtime_tool(tool_name, allow_python_fallback=False)
        if not command:
            missing.append(tool_name)

    return missing


def check_yt_dlp() -> bool:
    """Return True if yt-dlp can be resolved for the current runtime mode."""
    return build_yt_dlp_command(allow_python_fallback=True) is not None


def _tool_diagnostics(tool_name: str) -> dict[str, Any]:
    if tool_name == "yt-dlp":
        resolved_command = build_yt_dlp_command(allow_python_fallback=True)
    else:
        resolved_command = resolve_runtime_tool(tool_name, allow_python_fallback=False)

    bundled_binary = find_bundled_binary(tool_name)
    system_binary = find_system_binary(tool_name)

    diagnostics: dict[str, Any] = {
        "bundled": bundled_binary,
        "system": system_binary,
        "resolved_command": resolved_command,
        "available": bool(resolved_command),
    }

    if bundled_binary:
        try:
            diagnostics["bundled_size_bytes"] = os.path.getsize(bundled_binary)
        except OSError:
            pass

    return diagnostics


def get_runtime_diagnostics() -> dict[str, Any]:
    """Return a structured snapshot of resource/tool resolution state."""
    return {
        "app_name": APP_NAME,
        "frozen": is_frozen_runtime(),
        "platform": sys.platform,
        "executable": sys.executable,
        "resource_search_dirs": [str(path) for path in get_resource_search_dirs()],
        "runtime_bin_search_dirs": [str(path) for path in get_runtime_bin_search_dirs()],
        "runtime_manifest": get_runtime_manifest(),
        "tools": {
            tool_name: _tool_diagnostics(tool_name)
            for tool_name in RELEASE_REQUIRED_TOOLS
        },
    }


def install_yt_dlp(progress_callback: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """
    Install yt-dlp via pip in source mode.

    Packaged builds are intentionally immutable and should be rebuilt instead.
    """
    if is_frozen_runtime():
        return False, (
            "Packaged builds cannot install dependencies at runtime. "
            "Download a complete release bundle instead."
        )

    try:
        if progress_callback:
            progress_callback("Starting installation...")

        command = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"]

        if progress_callback:
            progress_callback(f"Running: {' '.join(command)}")

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            **SUBPROCESS_TEXT_KWARGS,
        )

        output_lines: list[str] = []
        for line in process.stdout or []:
            clean_line = line.strip()
            if not clean_line:
                continue
            output_lines.append(clean_line)
            if progress_callback:
                progress_callback(clean_line)

        process.wait()

        if process.returncode == 0:
            if progress_callback:
                progress_callback("Installation completed successfully!")
            return True, "Installation successful"

        error_message = "\n".join(output_lines[-10:])
        return False, f"Installation failed:\n{error_message}"
    except Exception as exc:
        return False, f"Installation error: {exc}"
