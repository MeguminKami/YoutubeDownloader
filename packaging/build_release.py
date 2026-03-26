from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


DIST_NAME = "YTGrab"
ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a release bundle with PyInstaller.")
    parser.add_argument("--platform", required=True, choices=("windows", "linux"))
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

    icon_path = asset_dir / "YTGrab.ico"
    with Image.open(_logo_png()) as image:
        image.save(
            icon_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return icon_path


def _runtime_dir(path: str) -> Path:
    runtime_dir = Path(path).resolve()
    runtime_bin_dir = runtime_dir / "bin"
    if not runtime_bin_dir.is_dir():
        raise FileNotFoundError(f"Runtime tool directory is missing: {runtime_bin_dir}")
    return runtime_dir


def _expected_output(platform: str, dist_dir: Path) -> Path:
    return dist_dir / DIST_NAME


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
    env["YTG_APP_VERSION"] = args.version
    env["YTG_RUNTIME_DIR"] = str(runtime_dir)
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / ".pyinstaller-cache" / args.platform)

    if args.platform == "windows":
        env["YTG_WINDOWS_ICON"] = str(_build_windows_icon(asset_dir))

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
