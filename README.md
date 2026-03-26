<p align="center">
  <img src="ui/logo.png" alt="YTGrab Logo" width="120" height="120">
</p>

<h1 align="center">YTGrab</h1>

<p align="center">
  <strong>A modern, queue-based YouTube downloader for Windows and Linux</strong>
</p>

<p align="center">
  <a href="https://github.com/joaoc/YoutubeGrab/releases/latest">
    <img src="https://img.shields.io/badge/Download-Latest%20Release-cc0000?style=for-the-badge&logo=github" alt="Download">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%20|%20Linux-333333?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-555555?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10+-666666?style=flat-square&logo=python&logoColor=white" alt="Python">
</p>

---

## Overview

YTGrab provides a clean desktop interface for downloading YouTube videos and audio. Queue multiple items, choose your preferred quality, and download everything with a single click.

**No terminal required.** Just download, extract, and run.

---

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Download](#download) | Get the latest release |
| [Features](#features) | What YTGrab can do |
| [How to Use](#how-to-use) | Step-by-step guide |
| [Cookie Authentication](#cookie-authentication) | Access restricted content |
| [Troubleshooting](#troubleshooting) | Common issues and fixes |
| [For Developers](#for-developers) | Build from source |

---

## Download

### Ready-to-Use Releases

Download the latest version for your platform. No installation required — just extract and run.

| Platform | Download | Notes |
|----------|----------|-------|
| **Windows** | `YTGrab-vX.X.X-windows-x64.zip` | Standard release |
| **Windows Debug** | `YTGrab-vX.X.X-windows-x64-debug.zip` | Console window for troubleshooting |
| **Linux** | `YTGrab-vX.X.X-linux-x64.tar.gz` | x64 only |

<p align="center">
  <a href="https://github.com/joaoc/YoutubeGrab/releases/latest">
    <img src="https://img.shields.io/badge/Go%20to%20Releases-cc0000?style=for-the-badge" alt="Releases">
  </a>
</p>

### What's Included

Each release is fully self-contained with all required tools bundled:

```
YTGrab/
├── YTGrab.exe          # Main application
├── _internal/          # Python runtime
└── runtime/
    └── bin/
        ├── yt-dlp      # Video extraction
        ├── ffmpeg      # Media processing
        ├── ffprobe     # Format detection
        └── deno        # JavaScript runtime
```

---

## Features

### Core Functionality

| Feature | Description |
|---------|-------------|
| **Queue System** | Add multiple videos before downloading |
| **Video Download** | Choose from available quality options |
| **Audio Extraction** | Extract MP3 audio from any video |
| **Playlist Support** | Download entire playlists at once |
| **Playlist Merge** | Combine playlist items into a single file |
| **Progress Tracking** | Real-time download progress for each item |
| **Download History** | Track completed and failed downloads |
| **Thumbnail Cache** | Preview thumbnails for queued items |

### Supported Content

- Single videos
- YouTube Shorts
- Full playlists
- Age-restricted content (with cookies)
- Private videos (with cookies)

---

## How to Use

### Basic Workflow

```
1. Launch YTGrab
       ↓
2. Paste YouTube URL
       ↓
3. Click "Queue" to fetch video details
       ↓
4. Choose download type:
   • Video → Select quality/format
   • Audio → Select bitrate
       ↓
5. Add to queue (repeat for more items)
       ↓
6. Click "Download All"
       ↓
7. Select output folder
       ↓
8. Done!
```

### Download Types

| Type | Options | Output |
|------|---------|--------|
| **Video** | 144p to 4K+ (based on availability) | `.mp4`, `.webm`, `.mkv` |
| **Audio** | Various bitrates | `.mp3` |

### Status Indicators

| Status | Meaning |
|--------|---------|
| `Queued` | Waiting to download |
| `Downloading` | Currently in progress |
| `Completed` | Successfully finished |
| `Failed` | Error occurred (check logs) |

---

## Cookie Authentication

Some YouTube content requires account authentication:

- Age-restricted videos
- Private videos
- Member-only content

### How to Add Cookies

1. Click **Insert Cookies** in the top bar
2. Paste your `cookies.txt` content
3. The app validates cookies automatically

### Getting Cookies

Use a browser extension like **Get cookies.txt LOCALLY** to export your YouTube cookies in Netscape format.

### Cookie Storage Location

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\YTGrab\cookies.txt` |
| Linux | `~/.config/YTGrab/cookies.txt` |

---

## Troubleshooting

<details>
<summary><strong>"yt-dlp is not installed"</strong></summary>

This should not happen with release builds. If running from source, install dependencies:
```bash
pip install -r requirements.txt
```
</details>

<details>
<summary><strong>Cookie validation fails / "sign in to confirm you're not a bot"</strong></summary>

Your cookies have expired. Export fresh cookies from your browser and replace them in the app.
</details>

<details>
<summary><strong>"Requested format is not available"</strong></summary>

The selected quality option is no longer available. Choose a different quality and try again.
</details>

<details>
<summary><strong>Merge fails</strong></summary>

FFmpeg is required for merging video and audio streams. Release builds include FFmpeg automatically.
</details>

<details>
<summary><strong>JS challenge / runtime errors</strong></summary>

Some YouTube pages require JavaScript execution. Ensure the bundled Deno runtime is present in `runtime/bin/`.
</details>

---

## For Developers

<details>
<summary><strong>Click to expand developer documentation</strong></summary>

### Requirements

- Python 3.10+
- `yt-dlp`
- `customtkinter`
- `Pillow`
- `ffmpeg` and `ffprobe`

### Install from Source

```bash
git clone https://github.com/joaoc/YoutubeGrab.git
cd YoutubeGrab

python -m venv .venv
source .venv/bin/activate  # Linux
# or: .venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Building Releases

Install build dependencies:

```bash
pip install -r requirements-build.txt
```

Download runtime tools:

```bash
python packaging/download_runtime_tools.py --platform windows --output-dir .runtime/windows-x64
```

Build the release:

```bash
python packaging/build_release.py --platform windows --runtime-dir .runtime/windows-x64 --version v1.0.0
```

Validate the build:

```bash
python packaging/validate_release.py --platform windows --dist-dir dist
```

### Project Structure

```
YoutubeGrab/
├── main.py                 # Entry point
├── app.py                  # Main UI application
├── core/
│   ├── downloader.py       # yt-dlp/ffmpeg pipeline
│   ├── auth.py             # Cookie handling
│   ├── deps.py             # Runtime tool resolution
│   └── models.py           # Data models
├── packaging/
│   ├── download_runtime_tools.py
│   ├── build_release.py
│   └── validate_release.py
├── ui/
│   ├── dialogs.py          # UI dialogs
│   ├── theme.py            # Color system
│   └── visual_assets.py    # Generated assets
└── utils/
    ├── config_store.py     # Configuration storage
    ├── history_store.py    # Download history
    └── thumbnail_cache.py  # Thumbnail management
```

### Security Notes

The download pipeline includes:

- URL scheme and domain validation
- Localhost/private network blocking
- Output filename sanitization
- Subprocess timeouts and retries
- Partial file cleanup on cancellation

</details>

---

<p align="center">
  <sub>Built with Python, CustomTkinter, and yt-dlp</sub>
</p>
