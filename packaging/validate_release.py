from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "YoutubeGrab"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a built YoutubeGrab release artifact.")
    parser.add_argument("--platform", required=True, choices=("windows", "linux"))
    parser.add_argument("--dist-dir", required=True)
    parser.add_argument("--probe-url")
    return parser.parse_args()


def _artifact_root(platform: str, dist_dir: Path) -> Path:
    return dist_dir / APP_NAME


def _main_executable(platform: str, dist_dir: Path) -> Path:
    if platform == "windows":
        return dist_dir / APP_NAME / f"{APP_NAME}.exe"
    return dist_dir / APP_NAME / APP_NAME


def _debug_executable(platform: str, dist_dir: Path) -> Path | None:
    if platform == "windows":
        return dist_dir / APP_NAME / f"{APP_NAME}Debug.exe"
    return None


def _run_self_check(executable: Path, probe_url: str | None) -> dict:
    if not executable.is_file():
        raise FileNotFoundError(f"Expected executable was not produced: {executable}")

    command = [str(executable), "--self-check", "--json"]
    if probe_url:
        command.extend(["--probe-url", probe_url])

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Self-check failed for {executable}.\n"
            f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
        )

    payload = result.stdout.strip()
    json_start = payload.find("{")
    if json_start >= 0:
        payload = payload[json_start:]

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Self-check did not produce valid JSON for {executable}: {exc}\n{result.stdout}"
        ) from exc


def main() -> int:
    args = _parse_args()
    dist_dir = Path(args.dist_dir).resolve()
    artifact_root = _artifact_root(args.platform, dist_dir)
    if not artifact_root.exists():
        raise FileNotFoundError(f"Expected build artifact was not produced: {artifact_root}")

    main_report = _run_self_check(_main_executable(args.platform, dist_dir), args.probe_url)
    if not main_report.get("ok"):
        raise RuntimeError(json.dumps(main_report, indent=2))

    debug_executable = _debug_executable(args.platform, dist_dir)
    if debug_executable:
        debug_report = _run_self_check(debug_executable, None)
        if not debug_report.get("ok"):
            raise RuntimeError(json.dumps(debug_report, indent=2))

    summary = {
        "ok": main_report.get("ok"),
        "frozen": main_report.get("frozen"),
        "missing_bundled_tools": main_report.get("missing_bundled_tools"),
        "asset_checks": main_report.get("asset_checks"),
        "online_probe_valid": (main_report.get("online_probe") or {}).get("valid"),
        "tool_versions": {
            tool_name: {
                "ok": tool_result.get("ok"),
                "version": tool_result.get("version"),
            }
            for tool_name, tool_result in (main_report.get("tool_checks") or {}).items()
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
