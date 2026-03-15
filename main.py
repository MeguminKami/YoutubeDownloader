"""
YouTube Downloader Pro - Entry Point

Security Note: Admin elevation removed by default as it's not required
for normal download operations. Users can run as admin if needed for
specific download locations.
"""


def main():
    # Note: Admin elevation removed for security
    # Most download operations don't require admin rights
    # User can right-click and "Run as Administrator" if needed
    from app import YouTubeDownloaderApp
    app = YouTubeDownloaderApp()
    app.mainloop()

if __name__ == "__main__":
    main()