from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable


USER_AGENT = "YoutubeGrab-release-builder/1.0"
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and validate bundled runtime tools.")
    parser.add_argument("--platform", required=True, choices=("windows", "macos", "linux"))
    parser.add_argument("--arch", default="x64", choices=("x64",))
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response, open(destination, "wb") as handle:
        shutil.copyfileobj(response, handle)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_executable(path: Path) -> None:
    if sys.platform == "win32":
        return
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run_version(path: Path, args: list[str]) -> str:
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [str(path)] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        timeout=30,
        check=True,
    )
    return (result.stdout or result.stderr).strip().splitlines()[0]


def _latest_release(repo: str) -> dict:
    return _http_get_json(GITHUB_API.format(repo=repo))


def _pick_asset(release: dict, matcher: Callable[[str], bool]) -> dict:
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if matcher(name):
            return asset
    raise FileNotFoundError(f"Could not find a matching release asset in {release.get('html_url')}")


def _extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(destination)


def _extract_tar_xz(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:xz") as archive:
        archive.extractall(destination)


def _find_file(root: Path, file_name: str) -> Path:
    matches = sorted(path for path in root.rglob(file_name) if path.is_file())
    if not matches:
        raise FileNotFoundError(f"Could not find {file_name} under {root}")
    return matches[0]


def _github_binary_download(repo: str, matcher: Callable[[str], bool], destination: Path) -> tuple[Path, dict]:
    release = _latest_release(repo)
    asset = _pick_asset(release, matcher)
    _download_file(asset["browser_download_url"], destination)
    return destination, asset


def _install_yt_dlp(platform: str, bin_dir: Path) -> dict:
    candidate_names = {
        "windows": {"yt-dlp.exe"},
        "linux": {"yt-dlp_linux"},
        "macos": {"yt-dlp_macos", "yt-dlp"},
    }[platform]

    destination_name = "yt-dlp.exe" if platform == "windows" else "yt-dlp"
    output_path = bin_dir / destination_name

    file_path, asset = _github_binary_download(
        "yt-dlp/yt-dlp",
        lambda name: name in candidate_names,
        output_path,
    )
    _make_executable(file_path)

    return {
        "path": file_path,
        "asset_name": asset["name"],
        "source_url": asset["browser_download_url"],
        "version": _run_version(file_path, ["--version"]),
        "sha256": _sha256(file_path),
    }


def _install_deno(platform: str, bin_dir: Path, temp_dir: Path) -> dict:
    asset_name = {
        "windows": "deno-x86_64-pc-windows-msvc.zip",
        "linux": "deno-x86_64-unknown-linux-gnu.zip",
        "macos": "deno-x86_64-apple-darwin.zip",
    }[platform]

    archive_path = temp_dir / asset_name
    _, asset = _github_binary_download(
        "denoland/deno",
        lambda name: name == asset_name,
        archive_path,
    )

    extract_dir = temp_dir / "deno"
    extract_dir.mkdir(parents=True, exist_ok=True)
    _extract_zip(archive_path, extract_dir)

    binary_name = "deno.exe" if platform == "windows" else "deno"
    source_binary = _find_file(extract_dir, binary_name)
    target_binary = bin_dir / binary_name
    shutil.copy2(source_binary, target_binary)
    _make_executable(target_binary)

    return {
        "path": target_binary,
        "asset_name": asset["name"],
        "source_url": asset["browser_download_url"],
        "version": _run_version(target_binary, ["--version"]),
        "sha256": _sha256(target_binary),
    }


def _install_ffmpeg_windows(bin_dir: Path, temp_dir: Path) -> dict[str, dict]:
    archive_path = temp_dir / "ffmpeg-win64-gpl.zip"
    _, asset = _github_binary_download(
        "BtbN/FFmpeg-Builds",
        lambda name: "win64-gpl.zip" in name and "shared" not in name,
        archive_path,
    )

    extract_dir = temp_dir / "ffmpeg-windows"
    extract_dir.mkdir(parents=True, exist_ok=True)
    _extract_zip(archive_path, extract_dir)

    ffmpeg_binary = _find_file(extract_dir, "ffmpeg.exe")
    ffprobe_binary = _find_file(extract_dir, "ffprobe.exe")

    target_ffmpeg = bin_dir / "ffmpeg.exe"
    target_ffprobe = bin_dir / "ffprobe.exe"
    shutil.copy2(ffmpeg_binary, target_ffmpeg)
    shutil.copy2(ffprobe_binary, target_ffprobe)

    return {
        "ffmpeg": {
            "path": target_ffmpeg,
            "asset_name": asset["name"],
            "source_url": asset["browser_download_url"],
            "version": _run_version(target_ffmpeg, ["-version"]),
            "sha256": _sha256(target_ffmpeg),
        },
        "ffprobe": {
            "path": target_ffprobe,
            "asset_name": asset["name"],
            "source_url": asset["browser_download_url"],
            "version": _run_version(target_ffprobe, ["-version"]),
            "sha256": _sha256(target_ffprobe),
        },
    }


def _install_ffmpeg_linux(bin_dir: Path, temp_dir: Path) -> dict[str, dict]:
    archive_path = temp_dir / "ffmpeg-linux64-gpl.tar.xz"
    _, asset = _github_binary_download(
        "BtbN/FFmpeg-Builds",
        lambda name: "linux64-gpl.tar.xz" in name and "shared" not in name,
        archive_path,
    )

    extract_dir = temp_dir / "ffmpeg-linux"
    extract_dir.mkdir(parents=True, exist_ok=True)
    _extract_tar_xz(archive_path, extract_dir)

    ffmpeg_binary = _find_file(extract_dir, "ffmpeg")
    ffprobe_binary = _find_file(extract_dir, "ffprobe")

    target_ffmpeg = bin_dir / "ffmpeg"
    target_ffprobe = bin_dir / "ffprobe"
    shutil.copy2(ffmpeg_binary, target_ffmpeg)
    shutil.copy2(ffprobe_binary, target_ffprobe)
    _make_executable(target_ffmpeg)
    _make_executable(target_ffprobe)

    return {
        "ffmpeg": {
            "path": target_ffmpeg,
            "asset_name": asset["name"],
            "source_url": asset["browser_download_url"],
            "version": _run_version(target_ffmpeg, ["-version"]),
            "sha256": _sha256(target_ffmpeg),
        },
        "ffprobe": {
            "path": target_ffprobe,
            "asset_name": asset["name"],
            "source_url": asset["browser_download_url"],
            "version": _run_version(target_ffprobe, ["-version"]),
            "sha256": _sha256(target_ffprobe),
        },
    }


def _install_ffmpeg_macos(bin_dir: Path, temp_dir: Path) -> dict[str, dict]:
    ffmpeg_archive = temp_dir / "ffmpeg-macos.zip"
    ffprobe_archive = temp_dir / "ffprobe-macos.zip"

    ffmpeg_url = "https://evermeet.cx/ffmpeg/getrelease/zip"
    ffprobe_url = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"

    _download_file(ffmpeg_url, ffmpeg_archive)
    _download_file(ffprobe_url, ffprobe_archive)

    ffmpeg_extract = temp_dir / "ffmpeg-macos"
    ffprobe_extract = temp_dir / "ffprobe-macos"
    ffmpeg_extract.mkdir(parents=True, exist_ok=True)
    ffprobe_extract.mkdir(parents=True, exist_ok=True)

    _extract_zip(ffmpeg_archive, ffmpeg_extract)
    _extract_zip(ffprobe_archive, ffprobe_extract)

    ffmpeg_binary = _find_file(ffmpeg_extract, "ffmpeg")
    ffprobe_binary = _find_file(ffprobe_extract, "ffprobe")

    target_ffmpeg = bin_dir / "ffmpeg"
    target_ffprobe = bin_dir / "ffprobe"
    shutil.copy2(ffmpeg_binary, target_ffmpeg)
    shutil.copy2(ffprobe_binary, target_ffprobe)
    _make_executable(target_ffmpeg)
    _make_executable(target_ffprobe)

    return {
        "ffmpeg": {
            "path": target_ffmpeg,
            "asset_name": ffmpeg_binary.name,
            "source_url": ffmpeg_url,
            "version": _run_version(target_ffmpeg, ["-version"]),
            "sha256": _sha256(target_ffmpeg),
        },
        "ffprobe": {
            "path": target_ffprobe,
            "asset_name": ffprobe_binary.name,
            "source_url": ffprobe_url,
            "version": _run_version(target_ffprobe, ["-version"]),
            "sha256": _sha256(target_ffprobe),
        },
    }


def _install_ffmpeg(platform: str, bin_dir: Path, temp_dir: Path) -> dict[str, dict]:
    if platform == "windows":
        return _install_ffmpeg_windows(bin_dir, temp_dir)
    if platform == "linux":
        return _install_ffmpeg_linux(bin_dir, temp_dir)
    return _install_ffmpeg_macos(bin_dir, temp_dir)


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir).resolve()
    bin_dir = output_dir / "bin"

    if output_dir.exists():
        shutil.rmtree(output_dir)

    bin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "platform": args.platform,
        "arch": args.arch,
        "tools": {},
    }

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)

        ytdlp = _install_yt_dlp(args.platform, bin_dir)
        deno = _install_deno(args.platform, bin_dir, temp_dir)
        ffmpeg_tools = _install_ffmpeg(args.platform, bin_dir, temp_dir)

    manifest["tools"]["yt-dlp"] = {
        **{key: value for key, value in ytdlp.items() if key != "path"},
        "relative_path": os.path.relpath(ytdlp["path"], output_dir).replace("\\", "/"),
    }
    manifest["tools"]["deno"] = {
        **{key: value for key, value in deno.items() if key != "path"},
        "relative_path": os.path.relpath(deno["path"], output_dir).replace("\\", "/"),
    }

    for tool_name, payload in ffmpeg_tools.items():
        manifest["tools"][tool_name] = {
            **{key: value for key, value in payload.items() if key != "path"},
            "relative_path": os.path.relpath(payload["path"], output_dir).replace("\\", "/"),
        }

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
