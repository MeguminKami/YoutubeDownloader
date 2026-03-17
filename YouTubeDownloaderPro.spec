# -*- mode: python ; coding: utf-8 -*-

import os
import shutil
import sys
import sysconfig


def _spec_dir() -> str:
    # PyInstaller may execute spec files without defining __file__.
    spec_path = globals().get('__file__') or globals().get('SPEC')
    if spec_path:
        return os.path.dirname(os.path.abspath(spec_path))

    spec_dir = globals().get('SPECPATH')
    if spec_dir:
        return os.path.abspath(spec_dir)

    if sys.argv and sys.argv[-1].lower().endswith('.spec'):
        return os.path.dirname(os.path.abspath(sys.argv[-1]))

    return os.path.abspath(os.getcwd())


def _asset_path(*parts: str) -> str:
    return os.path.join(_spec_dir(), *parts)


def _resolve_windows_icon() -> str:
    icon_path = _asset_path('ui', 'logo.ico')
    if os.path.isfile(icon_path):
        return icon_path

    png_path = _asset_path('ui', 'logo.png')
    if not os.path.isfile(png_path):
        raise SystemExit('Missing icon asset: ui/logo.png')

    try:
        from PIL import Image
        with Image.open(png_path) as icon_source:
            icon_source.save(icon_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])
    except Exception as exc:
        raise SystemExit(f'Unable to create ui/logo.ico from ui/logo.png: {exc}')

    if not os.path.isfile(icon_path):
        raise SystemExit('Unable to resolve icon asset: ui/logo.ico')
    return icon_path


def _windows_runtime_binary(name: str) -> str:
    env_var = f"{name.upper().replace('-', '')}_EXE"
    env_candidate = os.environ.get(env_var)

    scripts_dir = sysconfig.get_path('scripts')
    candidates = [
        env_candidate,
        os.path.join(scripts_dir, f'{name}.exe') if scripts_dir else None,
        shutil.which(f'{name}.exe'),
        shutil.which(name),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise SystemExit(f"Missing required Windows runtime tool for packaging: {name}.exe")


windows_binaries = []
windows_icon = None
if os.name == 'nt':
    windows_binaries = [
        (_windows_runtime_binary('yt-dlp'), '.'),
        (_windows_runtime_binary('ffmpeg'), '.'),
        (_windows_runtime_binary('ffprobe'), '.'),
    ]
    windows_icon = _resolve_windows_icon()


a = Analysis(
    [_asset_path('main.py')],
    pathex=[],
    binaries=windows_binaries,
    datas=[(_asset_path('ui', 'logo.png'), 'ui')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='YouTubeDownloaderPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=windows_icon,
)
