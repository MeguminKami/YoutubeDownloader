"""
YouTube Downloader Pro - Entry Point

Security Note: Admin elevation removed by default as it's not required
for normal download operations. Users can run as admin if needed for
specific download locations.
"""

import os


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
    _enable_high_dpi()
    from app import YoutubeGrabApp
    app = YoutubeGrabApp()
    app.mainloop()

if __name__ == "__main__":
    main()
