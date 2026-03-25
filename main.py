"""
YoutubeGrab application entrypoint and release self-check helpers.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

from core.deps import (
    RELEASE_REQUIRED_TOOLS,
    SOURCE_REQUIRED_TOOLS,
    build_yt_dlp_command,
    find_bundled_resource,
    get_missing_bundled_tools,
    get_runtime_diagnostics,
    is_frozen_runtime,
    resolve_runtime_tool,
)


TOOL_VERSION_ARGS = {
    "yt-dlp": ["--version"],
    "ffmpeg": ["-version"],
    "ffprobe": ["-version"],
    "deno": ["--version"],
}


def _print_startup_diagnostics() -> None:
    """Print runtime diagnostics when explicitly requested for troubleshooting."""
    if not is_frozen_runtime() or not os.environ.get("YTG_STARTUP_DIAGNOSTICS"):
        return

    diagnostics = get_runtime_diagnostics()
    print("=" * 60)
    print("YoutubeGrab - Startup Diagnostics")
    print("=" * 60)
    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    print("=" * 60)


def _enable_high_dpi() -> None:
    """Enable Windows DPI awareness so Tk is rendered sharply on scaled displays."""
    if os.name != "nt":
        return

    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _version_command_for_tool(tool_name: str) -> list[str] | None:
    if tool_name == "yt-dlp":
        return build_yt_dlp_command(allow_python_fallback=True)
    return resolve_runtime_tool(tool_name, allow_python_fallback=False)


def _run_tool_check(tool_name: str) -> dict[str, Any]:
    required_tools = RELEASE_REQUIRED_TOOLS if is_frozen_runtime() else SOURCE_REQUIRED_TOOLS
    command = _version_command_for_tool(tool_name)
    report: dict[str, Any] = {
        "required": tool_name in required_tools,
        "command": command,
        "ok": False,
    }

    if not command:
        report["error"] = "tool could not be resolved"
        return report

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    stdin_pipe = subprocess.DEVNULL if is_frozen_runtime() else None

    try:
        result = subprocess.run(
            command + TOOL_VERSION_ARGS[tool_name],
            capture_output=True,
            stdin=stdin_pipe,
            creationflags=creationflags,
            timeout=30,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        return report

    output = (result.stdout or result.stderr or "").strip()
    version_line = output.splitlines()[0] if output else ""

    report["returncode"] = result.returncode
    report["version"] = version_line
    report["stdout"] = (result.stdout or "").strip()[:400]
    report["stderr"] = (result.stderr or "").strip()[:400]
    report["ok"] = result.returncode == 0
    if result.returncode != 0:
        report["error"] = version_line or "tool exited with a non-zero status"
    return report


def run_self_check(probe_url: str | None = None) -> dict[str, Any]:
    """Run a packaging-oriented self-check and return a JSON-serializable report."""
    diagnostics = get_runtime_diagnostics()
    logo_path = find_bundled_resource("ui", "logo.png")

    report: dict[str, Any] = {
        "ok": True,
        "frozen": is_frozen_runtime(),
        "asset_checks": {
            "ui/logo.png": {
                "ok": bool(logo_path),
                "path": logo_path,
            },
        },
        "missing_bundled_tools": get_missing_bundled_tools(),
        "tool_checks": {
            tool_name: _run_tool_check(tool_name)
            for tool_name in TOOL_VERSION_ARGS
        },
        "runtime_diagnostics": diagnostics,
    }

    if report["missing_bundled_tools"]:
        report["ok"] = False

    for asset_result in report["asset_checks"].values():
        if not asset_result.get("ok"):
            report["ok"] = False

    for tool_result in report["tool_checks"].values():
        if tool_result.get("required") and not tool_result.get("ok"):
            report["ok"] = False

    if probe_url:
        try:
            from core.downloader import Downloader

            probe = Downloader().probe_cookie_validity_with_list_formats(probe_url)
            report["online_probe"] = probe
            if not probe.get("valid"):
                report["ok"] = False
        except Exception as exc:
            report["online_probe"] = {
                "valid": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
            report["ok"] = False

    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--probe-url")
    args, _ = parser.parse_known_args(argv)
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.self_check:
        report = run_self_check(probe_url=args.probe_url)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    _print_startup_diagnostics()
    _enable_high_dpi()

    from app import YoutubeGrabApp

    app = YoutubeGrabApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
