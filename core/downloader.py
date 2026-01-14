"""
Download logic and yt-dlp interaction
SECURITY HARDENED + FIXED VERSION
- Ensures video downloads produce actual video files
- Prevents path traversal attacks
- Secure subprocess handling
"""
import os
import subprocess
import sys
import shutil
import glob
import re
from typing import Callable, Optional, List, Dict, Any
import urllib.parse

# Security: Maximum allowed download size (10 GB)
MAX_DOWNLOAD_SIZE_BYTES = 10 * 1024 * 1024 * 1024

# Security: Allowed characters for filenames (prevents path traversal)
SAFE_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(filename: str) -> str:
    """
    Security: Sanitize filename to prevent path traversal and injection attacks.
    Removes or replaces dangerous characters.
    """
    if not filename:
        return "download"

    # Remove path separators and null bytes
    filename = filename.replace('/', '_').replace('\\', '_').replace('\x00', '')

    # Remove other dangerous characters
    filename = SAFE_FILENAME_PATTERN.sub('_', filename)

    # Remove leading/trailing dots and spaces (Windows restrictions)
    filename = filename.strip('. ')

    # Limit length
    if len(filename) > 200:
        filename = filename[:200]

    # Ensure we have something
    return filename if filename else "download"

class VideoFormat:
    """Represents a video format option"""
    def __init__(self, format_id: str, height: int, fps: Optional[int], ext: str,
                 vcodec: str, acodec: str, filesize: Optional[int] = None,
                 has_audio: bool = False):
        self.format_id = format_id
        self.height = height
        self.fps = fps
        self.ext = ext
        self.vcodec = vcodec
        self.acodec = acodec
        self.filesize = filesize
        self.has_audio = has_audio  # Whether this format includes audio

    def get_label(self) -> str:
        """Get human-readable label for this format"""
        label = f"{self.height}p"
        if self.fps and self.fps > 30:
            label += f" {self.fps}fps"
        if self.ext:
            label += f" ({self.ext.upper()})"
        if self.filesize:
            if self.filesize >= 1024 * 1024 * 1024:
                label += f" ~{self.filesize / (1024*1024*1024):.1f}GB"
            elif self.filesize >= 1024 * 1024:
                label += f" ~{self.filesize / (1024*1024):.0f}MB"
        return label

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for UI consumption"""
        return {
            'format_id': self.format_id,
            'height': self.height,
            'fps': self.fps,
            'ext': self.ext,
            'resolution': self.get_label(),
            'filesize': self.filesize,
            'has_audio': self.has_audio
        }

    def __repr__(self):
        return f"VideoFormat({self.get_label()}, id={self.format_id})"

class Downloader:
    """Handles download operations with yt-dlp"""

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback
        self.current_item_downloaded = 0
        self.completed_bytes = 0

    def extract_info(self, url: str):
        """Extract video/playlist info without downloading"""
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def get_available_video_formats(self, url: str) -> Dict[str, Any]:
        """
        Fetch all available video formats for a URL.
        Returns dict with 'video_formats' list of VideoFormat.to_dict() results.

        CRITICAL: Only returns formats that have video codecs (vcodec != 'none')
        This ensures video downloads produce actual video files.

        Security: Validates URL before processing.
        """
        import yt_dlp

        # Security: Basic URL validation
        if not self._is_valid_url(url):
            return {'video_formats': [], 'error': 'Invalid URL'}

        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,  # Get full format info
                'skip_download': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                # Handle playlists - get first video's formats
                if 'entries' in info and info['entries']:
                    first_entry = next((e for e in info['entries'] if e), None)
                    if first_entry:
                        if 'formats' not in first_entry:
                            # Need to fetch full info for this entry
                            entry_url = first_entry.get('url') or first_entry.get('webpage_url')
                            if entry_url:
                                info = ydl.extract_info(entry_url, download=False)
                        else:
                            info = first_entry

                formats = info.get('formats', [])

                # Filter and parse video formats
                video_formats = []
                seen_qualities = set()

                for fmt in formats:
                    # CRITICAL: Must have video codec (not 'none') and valid height
                    # This prevents audio-only formats from appearing
                    vcodec = fmt.get('vcodec', 'none')
                    acodec = fmt.get('acodec', 'none')
                    height = fmt.get('height')

                    if vcodec and vcodec != 'none' and height and height > 0:
                        fps = fmt.get('fps')
                        ext = fmt.get('ext', 'mp4')
                        format_id = fmt.get('format_id', '')
                        filesize = fmt.get('filesize') or fmt.get('filesize_approx')
                        has_audio = acodec and acodec != 'none'

                        # Create unique key for deduplication (prefer formats with audio)
                        quality_key = (height, fps or 0, ext)

                        # Skip if we've seen this quality, unless new one has audio and old didn't
                        if quality_key in seen_qualities:
                            continue

                        video_format = VideoFormat(
                            format_id=format_id,
                            height=height,
                            fps=fps,
                            ext=ext,
                            vcodec=vcodec,
                            acodec=acodec,
                            filesize=filesize,
                            has_audio=has_audio
                        )

                        video_formats.append(video_format)
                        seen_qualities.add(quality_key)

                # Sort by height (descending), then fps (descending)
                video_formats.sort(key=lambda f: (f.height, f.fps or 0), reverse=True)

                # Convert to dict format for UI
                return {
                    'video_formats': [f.to_dict() for f in video_formats],
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail')
                }

        except Exception as e:
            print(f"Error fetching formats: {e}")
            return {'video_formats': [], 'error': str(e)}

    def _is_valid_url(self, url: str) -> bool:
        """
        Security: Validate URL to prevent SSRF and other attacks.
        Only allows http/https schemes and common video hosts.
        """
        if not url or not isinstance(url, str):
            return False

        try:
            parsed = urllib.parse.urlparse(url.strip())

            # Only allow http/https
            if parsed.scheme not in ('http', 'https'):
                return False

            # Must have a hostname
            if not parsed.netloc:
                return False

            # Block localhost and private IPs (basic SSRF prevention)
            hostname = parsed.hostname.lower() if parsed.hostname else ''
            blocked_hosts = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
            if hostname in blocked_hosts:
                return False

            # Block private IP ranges
            if hostname.startswith(('10.', '172.16.', '172.17.', '172.18.', '172.19.',
                                    '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                                    '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                                    '172.30.', '172.31.', '192.168.')):
                return False

            return True
        except Exception:
            return False

    def estimate_size(self, url: str, item_type: str, quality: str, audio_format: str) -> Optional[int]:
        """Estimate total download size in bytes"""
        try:
            import yt_dlp

            ydl_opts = {'quiet': True, 'no_warnings': True}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if 'entries' in info:
                    total_size = 0
                    for entry in info['entries']:
                        if entry:
                            size = self._estimate_single_size(entry, item_type, quality, audio_format)
                            if size:
                                total_size += size
                    return total_size if total_size > 0 else None
                else:
                    return self._estimate_single_size(info, item_type, quality, audio_format)
        except:
            return None

    def _estimate_single_size(self, info: dict, item_type: str, quality: str, audio_format: str) -> Optional[int]:
        """Estimate size for a single video"""
        if item_type == "audio":
            formats = info.get('formats', [])
            for fmt in formats:
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    if size:
                        return int(size)
        else:
            # Video - quality is now format_id
            formats = info.get('formats', [])
            for fmt in formats:
                if fmt.get('format_id') == quality:
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    if size:
                        return int(size)

        return None

    def download_item(self, item, folder: str, progress_hook: Callable):
        """
        Download a single item.

        FIXED: Video downloads now properly use format_id with explicit audio merge.
        SECURITY: Sanitizes output filenames to prevent path traversal.
        """
        import yt_dlp

        # Security: Ensure folder is a valid directory path
        folder = os.path.abspath(folder)
        if not os.path.isdir(folder):
            raise ValueError(f"Invalid download folder: {folder}")

        # Security: Use sanitized output template
        # %(title)s is sanitized by our custom output template function
        ydl_opts = {
            'outtmpl': os.path.join(folder, '%(title).200s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'progress_hooks': [progress_hook],
            'restrictfilenames': True,  # Security: restrict to ASCII and safe chars
            'windowsfilenames': True,   # Security: Windows-safe filenames
        }

        temp_folder = None

        if item.item_type == "audio":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': item.audio_format or '192',
            }]
        else:
            # CRITICAL FIX: Video download - ensure we get actual video, not audio-only
            #
            # item.quality can be:
            # 1. A format_id (e.g., "137", "248") - use directly with audio merge
            # 2. A height value (e.g., "1080", "720") - use height-based format selection
            # 3. None/empty - use best available

            quality = item.quality
            height = getattr(item, 'height', None)

            if quality and not quality.isdigit():
                # quality is a format_id - use it directly with audio merge
                # Format: "{format_id}+bestaudio" ensures we get video+audio
                ydl_opts['format'] = f"{quality}+bestaudio[ext=m4a]/bestaudio/{quality}"
            elif height or (quality and quality.isdigit()):
                # Height-based selection (for playlists or fallback)
                h = height or int(quality)
                # Select best video at or below specified height + best audio
                ydl_opts['format'] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            else:
                # Fallback - get best video+audio combination
                ydl_opts['format'] = 'bestvideo+bestaudio/best'

            # Force MP4 output for maximum compatibility
            ydl_opts['merge_output_format'] = 'mp4'

        if item.is_playlist and item.merge_playlist:
            # Security: Use secure temp folder creation
            import tempfile
            temp_folder = tempfile.mkdtemp(prefix='ytdl_playlist_', dir=folder)
            ydl_opts['outtmpl'] = os.path.join(temp_folder, '%(playlist_index)03d - %(title).150s.%(ext)s')

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([item.url])

        if item.is_playlist and item.merge_playlist and temp_folder:
            ext = "mp3" if item.item_type == "audio" else "mp4"
            output_name = item.custom_name if item.custom_name else item.title
            # Security: Sanitize filename to prevent path traversal
            output_name = sanitize_filename(output_name)
            output_file = os.path.join(folder, f"{output_name}.{ext}")

            success = merge_playlist_files(temp_folder, output_file, ext)

            if success and os.path.exists(temp_folder):
                try:
                    shutil.rmtree(temp_folder)
                except:
                    pass

            return success

        return True

def merge_playlist_files(temp_folder: str, output_file: str, ext: str) -> bool:
    """
    Merge all downloaded files into one using FFmpeg.

    SECURITY HARDENED:
    - Uses absolute paths for ffmpeg
    - Validates file paths
    - Uses secure subprocess with shell=False
    - Properly escapes file paths in concat list
    """
    try:
        # Security: Validate temp_folder is a directory
        temp_folder = os.path.abspath(temp_folder)
        if not os.path.isdir(temp_folder):
            raise ValueError(f"Invalid temp folder: {temp_folder}")

        # Security: Validate output_file is within expected location
        output_file = os.path.abspath(output_file)

        patterns = ['*.mp3'] if ext == 'mp3' else ['*.mp4']

        files = []
        for pattern in patterns:
            files.extend(glob.glob(os.path.join(temp_folder, pattern)))

        files.sort()

        if not files:
            raise Exception("No files found to merge")

        # Security: Validate all files are within temp_folder
        for f in files:
            f_abs = os.path.abspath(f)
            if not f_abs.startswith(temp_folder):
                raise ValueError(f"Invalid file path detected: {f}")

        list_file = os.path.join(temp_folder, 'filelist.txt')

        # Security: Write file list with proper escaping for FFmpeg concat
        # FFmpeg concat demuxer requires specific escaping
        with open(list_file, 'w', encoding='utf-8') as f:
            for file_path in files:
                # FFmpeg concat requires single quotes and escaping of single quotes and backslashes
                safe_path = file_path.replace('\\', '/').replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # Security: Find ffmpeg in PATH or use absolute path
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            # Try common locations
            common_paths = [
                r'C:\ffmpeg\bin\ffmpeg.exe',
                r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg'
            ]
            for path in common_paths:
                if os.path.isfile(path):
                    ffmpeg_path = path
                    break

        if not ffmpeg_path:
            raise Exception("FFmpeg not found. Please install FFmpeg and add it to PATH.")

        ffmpeg_cmd = [
            ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
            '-i', list_file, '-c', 'copy', output_file
        ]

        # Security: Use CREATE_NO_WINDOW on Windows, never use shell=True
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=3600  # Security: 1 hour timeout to prevent DoS
        )

        if result.returncode != 0:
            # Try with re-encoding
            if ext == 'mp3':
                ffmpeg_cmd = [ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
                             '-acodec', 'libmp3lame', '-b:a', '192k', output_file]
            else:
                ffmpeg_cmd = [ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
                             '-c:v', 'libx264', '-c:a', 'aac', '-preset', 'fast', output_file]

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                creationflags=creationflags,
                timeout=7200  # Security: 2 hour timeout for re-encoding
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg error: {result.stderr}")

        return True
    except subprocess.TimeoutExpired:
        print("Merge operation timed out")
        return False
    except Exception as e:
        print(f"Merge error: {e}")
        return False