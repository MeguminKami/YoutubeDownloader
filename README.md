# YoutubeGrab

A modern desktop YouTube downloader built with Python and CustomTkinter.

YoutubeGrab gives you a clean queue-based workflow for downloading videos or audio, with progress tracking, cookie-based authentication support, and persistent history.

## Highlights

- Clean desktop UI built with `customtkinter`
- Queue multiple items before starting downloads
- Download as video or extract audio (`mp3`)
- Format-aware quality picker based on `yt-dlp --list-formats`
- Supports single videos and playlists
- Optional playlist merge (single output file)
- Cookie input and validation flow for restricted/private videos
- Download history with saved metadata and thumbnail caching
- Cancel-in-progress with session file cleanup

## Requirements

- Python 3.10+ (recommended)
- `yt-dlp`
- `customtkinter`
- `Pillow`
- `ffmpeg` and `ffprobe` (required for merge workflows)

Project dependencies from `requirements.txt`:

- `customtkinter>=5.2.0`
- `yt-dlp>=2024.11.18`
- `Pillow>=10.2.0`

## Install (source)

```bat
cd C:\Users\joaoc\Desktop\Projetos\YoutubeGrab
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bat
cd C:\Users\joaoc\Desktop\Projetos\YoutubeGrab
python main.py
```

## How to Use

1. Launch the app.
2. Paste a YouTube URL (video, shorts, or playlist).
3. Click **Queue** to fetch details and open options.
4. Choose download type:
   - **Video**: pick quality/format
   - **Audio**: choose bitrate
5. Add item(s) to queue.
6. Click **Download All** and choose an output folder.

The app tracks each item status (`queued`, `downloading`, `completed`, `failed`) and saves completed/failed history entries.

## Cookies Authentication

Some YouTube content requires account cookies. YoutubeGrab includes a cookie workflow in-app:

- Use the **Insert Cookies** button in the top bar.
- Paste or replace `cookies.txt` content.
- The app validates cookies using a `yt-dlp` probe request.

Runtime cookie location is managed by `core/auth.py` and `utils/config_store.py`, typically under:

- `%APPDATA%\YTGrab` (Windows)
- `~/.config/YTGrab` (fallback)
- `./.ytgrab` (fallback)

## FFmpeg Notes

`ffmpeg`/`ffprobe` are required when:

- Selected quality uses separate video-only + audio-only streams
- Merging playlist items into one final file

If FFmpeg is missing, the app raises a clear error and keeps the queue for retry.

## Packaging (Windows executable)

The repository includes `YoutubeGrab.spec` for PyInstaller builds.

```bat
cd C:\Users\joaoc\Desktop\Projetos\YoutubeGrab
pyinstaller YoutubeGrab.spec
```

On Windows, this spec now generates two executables in `dist/`:

- `YoutubeGrab.exe` (normal GUI build)
- `YoutubeGrabDev.exe` (debug build with console/terminal output)

Release Windows zip artifacts include both executables so you can run `YoutubeGrabDev.exe` when you need startup/runtime logs.

The spec expects Windows runtime tools to be available (or provided via env vars):

- `yt-dlp.exe`
- `ffmpeg.exe`
- `ffprobe.exe`

Optional explicit environment variables recognized by the spec:

- `YTDLP_EXE`
- `FFMPEG_EXE`
- `FFPROBE_EXE`

## Troubleshooting

- **"yt-dlp is not installed"**
  - Install dependencies with `pip install -r requirements.txt`.

- **Cookie validation fails / "sign in to confirm you're not a bot"**
  - Refresh and replace `cookies.txt` from a logged-in browser session.

- **"Requested format is not available"**
  - The selected format changed upstream; choose another quality and retry.

- **Merge fails**
  - Confirm `ffmpeg` and `ffprobe` are installed and accessible.

- **Packaged build reports missing tools**
  - Rebuild or reinstall with all required bundled binaries.

## Security and Robustness Notes

Current download pipeline includes safeguards such as:

- URL scheme/domain validation
- Blocking localhost/private-network targets
- Output filename sanitization
- Controlled subprocess invocation with timeouts/retries
- Cleanup of partial files on cancellation

## Project Structure

```text
YoutubeGrab/
  app.py                # Main UI app
  main.py               # Entry point
  core/
    downloader.py       # yt-dlp/ffmpeg pipeline and format logic
    auth.py             # cookies.txt handling and validation
    deps.py             # runtime tool resolution and checks
    models.py           # queue/history dataclasses
  ui/
    dialogs.py          # Installer/options/progress dialogs
    theme.py            # color system
    visual_assets.py    # generated icons/tiles/images
  utils/
    config_store.py     # app data + JSON state storage
    history_store.py    # persistent download history
    thumbnail_cache.py  # cached thumbnail management
```

## Development Notes

- Entry point: `main.py`
- Main window class: `YoutubeGrabApp` in `app.py`
- Core downloader class: `Downloader` in `core/downloader.py`

