"""
Dependency checking and installation for yt-dlp
"""
import sys
import subprocess
from typing import Callable, Optional

def check_yt_dlp() -> bool:
    """Check if yt-dlp is installed"""
    try:
        import yt_dlp
        return True
    except ImportError:
        return False

def install_yt_dlp(progress_callback: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """
    Install yt-dlp using pip
    Returns (success, message)
    """
    try:
        if progress_callback:
            progress_callback("Starting installation...")

        cmd = [sys.executable, "-m", "pip", "install", "yt-dlp"]

        if progress_callback:
            progress_callback(f"Running: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
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