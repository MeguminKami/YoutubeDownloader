# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


def _spec_root() -> Path:
    spec_path = globals().get("__file__") or globals().get("SPEC")
    if spec_path:
        return Path(spec_path).resolve().parent

    spec_dir = globals().get("SPECPATH")
    if spec_dir:
        return Path(spec_dir).resolve()

    return Path.cwd().resolve()


ROOT = _spec_root()
APP_NAME = os.environ.get("YTG_APP_NAME", "YoutubeGrab")
APP_VERSION = os.environ.get("YTG_APP_VERSION", "0.0.0")
RUNTIME_DIR = Path(os.environ.get("YTG_RUNTIME_DIR", ROOT / ".runtime")).resolve()
WINDOWS_ICON = os.environ.get("YTG_WINDOWS_ICON")


def _dedupe_entries(entries):
    seen = set()
    deduped = []
    for source, dest in entries:
        key = (str(source), str(dest))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((str(source), str(dest)))
    return deduped


def _runtime_tool_entries():
    """Return runtime tools as datas (not binaries) to avoid PyInstaller processing.

    Adding these as binaries causes PyInstaller to analyze/modify them, which corrupts
    executables like yt-dlp that are themselves PyInstaller onefile bundles.
    """
    entries = []
    runtime_bin_dir = RUNTIME_DIR / "bin"
    if runtime_bin_dir.is_dir():
        for path in sorted(runtime_bin_dir.iterdir()):
            if path.is_file():
                entries.append((str(path), os.path.join("runtime", "bin")))
    return entries


datas = [
    (str(ROOT / "ui" / "logo.png"), "ui"),
]
datas.extend(_runtime_tool_entries())
binaries = []
hiddenimports = [
    "PIL._tkinter_finder",
    "PIL.ImageTk",
]


for package_name in ("customtkinter", "yt_dlp", "yt_dlp_ejs"):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    except Exception:
        continue

    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)


manifest_path = RUNTIME_DIR / "manifest.json"
if manifest_path.is_file():
    datas.append((str(manifest_path), "runtime"))


a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=_dedupe_entries(binaries),
    datas=_dedupe_entries(datas),
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)


if sys.platform == "win32":
    gui_exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=WINDOWS_ICON or None,
    )

    debug_exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=f"{APP_NAME}Debug",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=WINDOWS_ICON or None,
    )

    coll = COLLECT(
        gui_exe,
        debug_exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )

else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name=APP_NAME,
    )
