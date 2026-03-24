"""
Dependency checking and installation for yt-dlp
"""
import os
import shutil
import sys
import subprocess
from typing import Callable, List, Optional


SUBPROCESS_TEXT_KWARGS = {
    'text': True,
    'encoding': 'utf-8',
    'errors': 'replace',
}


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def _runtime_dir() -> str:
    if is_frozen_runtime():
        meipass_dir = getattr(sys, "_MEIPASS", None)
        if meipass_dir:
            return meipass_dir
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(__file__))


def _runtime_search_dirs() -> List[str]:
    """Return runtime directories to probe for bundled tools in priority order."""
    if not is_frozen_runtime():
        return [_runtime_dir()]

    search_dirs: List[str] = []
    meipass_dir = getattr(sys, "_MEIPASS", None)
    executable_dir = os.path.dirname(sys.executable)
    for candidate in (meipass_dir, executable_dir):
        if candidate and candidate not in search_dirs:
            search_dirs.append(candidate)
    return search_dirs


def _binary_candidates(tool_name: str) -> List[str]:
    if os.name == 'nt':
        return [f"{tool_name}.exe", tool_name]
    return [tool_name]


def find_bundled_binary(tool_name: str) -> Optional[str]:
    """Return bundled binary path when present in frozen app directory."""
    for base_dir in _runtime_search_dirs():
        for candidate in _binary_candidates(tool_name):
            candidate_path = os.path.join(base_dir, candidate)
            if os.path.isfile(candidate_path):
                return candidate_path
    return None


def get_missing_bundled_tools() -> List[str]:
    """Return missing required bundled binaries in frozen mode."""
    if not is_frozen_runtime():
        return []

    required_tools = ['yt-dlp']
    if os.name == 'nt':
        required_tools.extend(['ffmpeg', 'ffprobe'])

    missing = []
    for tool in required_tools:
        if not find_bundled_binary(tool):
            missing.append(tool)
    return missing

def check_yt_dlp() -> bool:
    """Check if yt-dlp is installed"""
    if is_frozen_runtime():
        return find_bundled_binary('yt-dlp') is not None

    if shutil.which('yt-dlp'):
        return True

    try:
        import yt_dlp
        return True
    except ImportError:
        return False


def get_runtime_diagnostics() -> dict:
    """
    Return diagnostic information about the runtime environment.
    Useful for debugging frozen build issues.
    """
    import logging

    diagnostics = {
        'frozen': is_frozen_runtime(),
        'platform': sys.platform,
        'executable': sys.executable,
    }

    if is_frozen_runtime():
        meipass = getattr(sys, '_MEIPASS', None)
        diagnostics['meipass'] = meipass
        diagnostics['search_dirs'] = _runtime_search_dirs()

        # Check bundled binaries
        for tool in ['yt-dlp', 'ffmpeg', 'ffprobe']:
            path = find_bundled_binary(tool)
            diagnostics[f'{tool}_path'] = path
            if path:
                diagnostics[f'{tool}_exists'] = os.path.isfile(path)
                diagnostics[f'{tool}_executable'] = os.access(path, os.X_OK) if path else False

        logging.debug(f"[diagnostics] Frozen runtime: {diagnostics}")
    else:
        diagnostics['yt_dlp_which'] = shutil.which('yt-dlp')
        diagnostics['ffmpeg_which'] = shutil.which('ffmpeg')

    return diagnostics

def install_yt_dlp(progress_callback: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """
    Install yt-dlp using pip
    Returns (success, message)
    """
    try:
        if is_frozen_runtime():
            return False, (
                "Packaged builds cannot install dependencies at runtime. "
                "Rebuild/reinstall a complete release that bundles yt-dlp, ffmpeg, and ffprobe."
            )

        if progress_callback:
            progress_callback("Starting installation...")

        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]

        if progress_callback:
            progress_callback(f"Running: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            **SUBPROCESS_TEXT_KWARGS,
        )

        output_lines = []
        for line in process.stdout:
            line = line.strip()
            if line:
                output_lines.append(line)
                if progress_callback:
                    progress_callback(line)

        process.wait()

        if process.returncode == 0:
            if progress_callback:
                progress_callback("✓ Installation completed successfully!")
            return True, "Installation successful"
        else:
            error_msg = '\n'.join(output_lines[-10:])
            return False, f"Installation failed:\n{error_msg}"

    except Exception as e:
        return False, f"Installation error: {str(e)}"
