"""
YoutubeGrab - Entry Point

Security Note: Admin elevation removed by default as it's not required
for normal download operations. Users can run as admin if needed for
specific download locations.
"""

import os
import sys


def _print_startup_diagnostics():
    """Print diagnostic info at startup for debugging frozen builds."""
    frozen = getattr(sys, 'frozen', False)
    if not frozen:
        return

    print("=" * 60)
    print("YoutubeGrab - Startup Diagnostics")
    print("=" * 60)
    print(f"Frozen: {frozen}")
    print(f"Executable: {sys.executable}")

    meipass = getattr(sys, '_MEIPASS', None)
    print(f"_MEIPASS: {meipass}")

    if meipass:
        # Check for bundled binaries
        for binary in ['yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe']:
            path = os.path.join(meipass, binary)
            exists = os.path.isfile(path)
            print(f"  {binary}: {'EXISTS' if exists else 'NOT FOUND'} at {path}")
    print("=" * 60)


def _enable_high_dpi():
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


def main():
    # Note: Admin elevation removed for security
    # Most download operations don't require admin rights
    # User can right-click and "Run as Administrator" if needed
    _print_startup_diagnostics()
    _enable_high_dpi()
    from app import YoutubeGrabApp
    app = YoutubeGrabApp()
    app.mainloop()

if __name__ == "__main__":
    main()
