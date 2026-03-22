# YTGrab Website Copy

## Product Overview

YTGrab is a desktop YouTube downloader built for a cleaner, more reliable workflow. Instead of acting like a simple paste-and-save tool, the current version gives users a full queue-based experience with format selection, playlist handling, thumbnail previews, progress tracking, and download history.

The app is designed for people who want more control before the download starts. Users can paste a YouTube link, review the media, choose between video and audio, select the quality they want, add one or more items to a queue, and then download everything in one organized batch.

## Short Description

YTGrab is a modern desktop app for downloading YouTube videos or audio with flexible quality selection, playlist support, queue management, live progress tracking, and saved download history.

## Longer Description

YTGrab helps users download YouTube content through a more polished desktop workflow.

It supports standard video links, Shorts, and playlists. After pasting a URL, the app loads the media information and lets the user choose how they want to download it. For video, YTGrab reads the available formats and presents quality options such as 360p, 480p, 720p, 1080p, and higher when available. For audio, the app exports MP3 and offers bitrate choices including 128 kbps, 192 kbps, 256 kbps, and 320 kbps.

The app is no longer limited to one item at a time. Users can build a queue with multiple downloads, review each item visually with title and thumbnail previews, and then start the entire batch at once. During downloads, YTGrab shows progress, estimated size, current speed, and status updates for each item.

Playlist handling is also much more capable in the current version. Users can select which playlist videos they want to keep, add them as separate queue items, or merge the chosen playlist entries into one final file when the workflow requires it.

Once downloads finish, YTGrab stores the results in a history view so users can quickly see completed or failed jobs and jump back to the original source link when needed.

## Core Features

- Download YouTube videos as MP4.
- Download YouTube audio as MP3.
- Choose from multiple video qualities based on real formats returned by yt-dlp.
- Choose audio bitrate presets from 128 kbps up to 320 kbps.
- Add multiple items to a download queue before starting.
- Support watch links, Shorts links, and playlist URLs.
- Preview titles, channels, durations, and thumbnails before downloading.
- Select specific videos from a playlist instead of downloading everything blindly.
- Optionally merge selected playlist items into one output when that mode is used.
- View live progress with queue position, current item status, total progress, and size estimation.
- Keep a persistent history of completed and failed downloads.
- Switch between dark and light themes.
- Use browser-exported `cookies.txt` when YouTube requires account verification or stricter access.

## Current User Flow

1. Paste a YouTube watch, Shorts, or playlist URL.
2. Open the download options dialog.
3. Choose `Video` or `Audio`.
4. Pick the preferred quality.
5. If the link is a playlist, choose which videos to keep and whether to download them separately or merge them.
6. Add the selection to the queue.
7. Start the batch download and choose the output folder.
8. Follow progress in the download dialog and review results in the history tab.

## What Makes This Version Better

- It is a full desktop workflow, not just a single download form.
- It gives users control over quality before the download begins.
- It handles multiple downloads in one queue.
- It supports playlists in a much more usable way.
- It includes thumbnail previews and richer item metadata.
- It saves history so past results are not lost after use.
- It provides cookie guidance for YouTube bot-detection or verification issues.

## Format and Quality Support

### Video

YTGrab reads the available video formats directly from YouTube through yt-dlp and presents the best usable option for each resolution. Depending on the source, users may see options like:

- 360p
- 480p
- 720p
- 1080p
- 1440p
- 2160p

Some qualities are ready to download directly, while others may require an audio merge if YouTube provides video and audio as separate streams.

### Audio

YTGrab converts audio downloads to MP3 and offers bitrate presets such as:

- 128 kbps
- 192 kbps
- 256 kbps
- 320 kbps

The default audio recommendation in the current app is 256 kbps as a balance between quality and file size.

## Playlist Support

The current app treats playlists as a first-class feature.

- Users can inspect the playlist after loading it.
- Users can choose specific entries instead of taking the whole list.
- Selected entries can be added to the queue as individual downloads.
- In merge mode, selected playlist items can be combined into one final file.

This makes the app much more flexible for music sets, lecture series, compilations, and curated download batches.

## Queue and History

The queue is central to the current version of YTGrab.

- Users can prepare several downloads before starting.
- Each queue item keeps its own settings, such as type, quality, title, and thumbnail.
- The progress window tracks the current item and the overall batch.
- Completed and failed items are stored in history for later review.

History also keeps useful context such as the source URL, output path when available, and the final result state.

## Authentication and Cookies

YTGrab includes built-in help for `cookies.txt` because YouTube can sometimes block downloads or require account verification.

If valid YouTube authentication cookies are present, the app can pass them to yt-dlp automatically. The interface also tells the user whether cookies are missing, invalid, expired, or ready to use. This makes troubleshooting much easier than in a basic downloader.

## Requirements and Notes

- The app uses `yt-dlp` as its download engine.
- The interface is built with `CustomTkinter`.
- `Pillow` is used for thumbnails and visual assets.
- `FFmpeg` is required for workflows that need stream merging, including some video qualities and playlist merge mode.
- Theme state and download history are saved locally so the app can restore that experience later.

## Suggested Homepage Copy

### Headline

Download YouTube videos and audio with a cleaner desktop workflow.

### Subheadline

YTGrab lets you choose MP4 or MP3, pick the quality you want, queue multiple downloads, manage playlists, and track everything from one polished desktop app.

### Feature Highlights

- Multiple video qualities, including higher resolutions when available
- MP3 export with selectable bitrate presets
- Queue-based batch downloading
- Playlist video selection and merge options
- Thumbnail previews and live progress tracking
- Persistent download history
- Cookie support for tougher YouTube authentication cases

## One-Paragraph Website Summary

YTGrab is a modern desktop YouTube downloader that gives users much more control than a basic converter. It supports MP4 video downloads, MP3 audio downloads, multiple quality options, playlist selection, batch queueing, thumbnail previews, live progress tracking, saved history, and optional `cookies.txt` support for more reliable access when YouTube asks for verification.

## Visual Art Style

The visual style for YTGrab should feel bold, minimal, and premium. It should instantly communicate speed, control, and a strong desktop-software identity instead of looking like a generic downloader or a busy tech mockup.

The core color palette should remain focused on black, red, and white. Black should carry most of the visual weight, red should act as the main energy accent, and white should be used for contrast, logo clarity, and title readability. The overall result should feel sharp, modern, and high-contrast.

The main hero image or cover artwork should feature the brand symbol clearly: a black claw holding a red-and-white play button inspired by the app logo. The claw should look powerful and precise, not horror-themed. It should suggest that YTGrab can "grab" and organize content quickly.

The composition should stay clean and simplistic, with one strong focal point, balanced spacing, and enough negative space for the `YTGrab` title. The title should use a modern bold style that feels fast, technical, and confident.

To communicate what the app does without cluttering the image, the artwork can include a few subtle quality cues such as `MP4`, `MP3`, `1080p`, `720p`, `320 kbps`, or `256 kbps`. These should appear as small polished visual accents rather than full UI panels.

The mood should feel fast, efficient, and controlled. Subtle motion lines, soft glow, and sleek contrast can help suggest performance, but the artwork should still remain simple, readable, and brand-focused.

The visual direction should avoid photorealism, excessive interface clutter, extra colors, horror styling, or a stock-image look. It should feel like focused promotional art built around the YTGrab identity.
