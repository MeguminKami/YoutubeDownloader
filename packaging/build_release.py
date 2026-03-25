from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_NAME = "YoutubeGrab"
ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a release bundle with PyInstaller.")
    parser.add_argument("--platform", required=True, choices=("windows", "macos", "linux"))
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist-dir", default=str(ROOT / "dist"))
    parser.add_argument("--work-dir", default=str(ROOT / "build" / "pyinstaller"))
    return parser.parse_args()


def _logo_png() -> Path:
    path = ROOT / "ui" / "logo.png"
    if not path.is_file():
        raise FileNotFoundError(f"Missing required logo asset: {path}")
    return path


def _build_asset_dir(platform: str) -> Path:
    asset_dir = ROOT / "build" / "release-assets" / platform
    asset_dir.mkdir(parents=True, exist_ok=True)
    return asset_dir


def _build_windows_icon(asset_dir: Path) -> Path:
    from PIL import Image

    icon_path = asset_dir / "YoutubeGrab.ico"
    with Image.open(_logo_png()) as image:
        image.save(
            icon_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return icon_path


def _build_macos_icon(asset_dir: Path) -> Path | None:
    iconutil = shutil.which("iconutil")
    if not iconutil:
        return None

    from PIL import Image

    icon_path = asset_dir / "YoutubeGrab.icns"

    with tempfile.TemporaryDirectory() as temp_dir:
        iconset_dir = Path(temp_dir) / "YoutubeGrab.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        size_map = {
            "icon_16x16.png": 16,
            "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32,
            "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128,
            "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256,
            "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512,
            "icon_512x512@2x.png": 1024,
        }

        with Image.open(_logo_png()) as image:
            rgba = image.convert("RGBA")
            for file_name, size in size_map.items():
                rgba.resize((size, size), Image.Resampling.LANCZOS).save(iconset_dir / file_name)

        subprocess.run(
            [iconutil, "-c", "icns", str(iconset_dir), "-o", str(icon_path)],
            check=True,
        )

    return icon_path if icon_path.is_file() else None


def _runtime_dir(path: str) -> Path:
    runtime_dir = Path(path).resolve()
    runtime_bin_dir = runtime_dir / "bin"
    if not runtime_bin_dir.is_dir():
        raise FileNotFoundError(f"Runtime tool directory is missing: {runtime_bin_dir}")
    return runtime_dir


def _expected_output(platform: str, dist_dir: Path) -> Path:
    if platform == "macos":
        return dist_dir / f"{APP_NAME}.app"
    return dist_dir / APP_NAME


def _set_execute_bits(bundle_path: Path) -> None:
    if sys.platform == "win32":
        return

    for candidate in bundle_path.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.parent.name != "bin" or candidate.parent.parent.name != "runtime":
            continue
        candidate.chmod(candidate.stat().st_mode | 0o755)


def main() -> int:
    args = _parse_args()
    runtime_dir = _runtime_dir(args.runtime_dir)
    dist_dir = Path(args.dist_dir).resolve()
    work_dir = Path(args.work_dir).resolve() / args.platform
    asset_dir = _build_asset_dir(args.platform)

    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    output_path = _expected_output(args.platform, dist_dir)
    if output_path.exists():
        if output_path.is_dir():
            shutil.rmtree(output_path)
        else:
            output_path.unlink()

    env = os.environ.copy()
    env["YTG_APP_NAME"] = APP_NAME
    env["YTG_APP_VERSION"] = args.version
    env["YTG_RUNTIME_DIR"] = str(runtime_dir)
    env["YTG_MACOS_BUNDLE_ID"] = "com.joaoc.youtubegrab"
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / ".pyinstaller-cache" / args.platform)

    if args.platform == "windows":
        env["YTG_WINDOWS_ICON"] = str(_build_windows_icon(asset_dir))
    elif args.platform == "macos":
        macos_icon = _build_macos_icon(asset_dir)
        if macos_icon:
            env["YTG_MACOS_ICON"] = str(macos_icon)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        str(ROOT / "YoutubeGrab.spec"),
    ]

    subprocess.run(command, cwd=ROOT, env=env, check=True)

    if not output_path.exists():
        raise FileNotFoundError(f"Expected PyInstaller output was not produced: {output_path}")

    _set_execute_bits(output_path)

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
