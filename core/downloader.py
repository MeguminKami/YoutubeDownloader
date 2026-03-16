"""
Download logic and yt-dlp interaction.

This module implements a format-driven pipeline:
- discover formats from `yt-dlp --list-formats URL`
- classify combined/video-only/audio-only streams
- build explicit download plans for selected quality
- execute yt-dlp commands internally with progress/stage callbacks
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from typing import Any, Callable, Dict, List, Optional


from core.models import DownloadPlan

# Security: Maximum allowed download size (10 GB)
MAX_DOWNLOAD_SIZE_BYTES = 10 * 1024 * 1024 * 1024

# Security: Allowed characters for filenames (prevents path traversal)
SAFE_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class DownloadPipelineError(RuntimeError):
    """Base exception for user-facing download pipeline failures."""

    def __init__(self, reason: str, code: str):
        super().__init__(reason)
        self.code = code


class FormatDiscoveryError(DownloadPipelineError):
    def __init__(self, reason: str):
        super().__init__(reason, "format_discovery_failed")


class NoCompatibleFormatError(DownloadPipelineError):
    def __init__(self, reason: str):
        super().__init__(reason, "no_compatible_format")


class MissingFFmpegError(DownloadPipelineError):
    def __init__(self, reason: str = "FFmpeg is required to merge video and audio streams."):
        super().__init__(reason, "missing_ffmpeg")


class DirectDownloadError(DownloadPipelineError):
    def __init__(self, reason: str):
        super().__init__(reason, "direct_download_failed")


class MergeFailureError(DownloadPipelineError):
    def __init__(self, reason: str):
        super().__init__(reason, "merge_failed")


class DownloadCancelledError(DownloadPipelineError):
    def __init__(self, reason: str = 'Download cancelled by user'):
        super().__init__(reason, "download_cancelled")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent traversal/injection attacks."""
    if not filename:
        return "download"

    filename = filename.replace('/', '_').replace('\\', '_').replace('\x00', '')
    filename = SAFE_FILENAME_PATTERN.sub('_', filename)
    filename = filename.strip('. ')

    if len(filename) > 200:
        filename = filename[:200]

    return filename if filename else "download"


class Downloader:
    """Handles download operations with yt-dlp."""

    _DOWNLOAD_PERCENT_RE = re.compile(r"\[download\]\s+(?P<pct>\d+(?:\.\d+)?)%")
    _DOWNLOAD_SPEED_RE = re.compile(r"\bat\s+(?P<speed>[^\s]+/s)")
    _DOWNLOAD_ETA_RE = re.compile(r"\bETA\s+(?P<eta>[0-9:]+)")
    _FPS_RE = re.compile(r"\b(?P<fps>\d+(?:\.\d+)?)fps\b", re.IGNORECASE)
    _HEIGHT_RE = re.compile(r"(?:\d{2,5}x(?P<h1>\d{2,5})|(?P<h2>\d{3,4})p)")
    _TBR_RE = re.compile(r"\b(?P<tbr>\d+(?:\.\d+)?)k\b", re.IGNORECASE)
    _SIZE_RE = re.compile(r"~?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[KMGT]i?B)")

    def __init__(self, progress_callback: Optional[Callable] = None):
        self.progress_callback = progress_callback

    def _snapshot_files(self, folder: str) -> set:
        paths = set()
        if not os.path.isdir(folder):
            return paths
        for root, _, files in os.walk(folder):
            for name in files:
                paths.add(os.path.abspath(os.path.join(root, name)))
        return paths

    def _safe_delete_file(self, file_path: str):
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception:
            pass

    def _cleanup_cancelled_download(self, folder: str, before_files: set, temp_folder: Optional[str] = None):
        current_files = self._snapshot_files(folder)
        for created_file in current_files - before_files:
            self._safe_delete_file(created_file)

        for pattern in ('*.part', '*.ytdl', '*.temp', '*.tmp'):
            for file_path in glob.glob(os.path.join(folder, '**', pattern), recursive=True):
                self._safe_delete_file(file_path)

        if temp_folder and os.path.exists(temp_folder):
            try:
                shutil.rmtree(temp_folder)
            except Exception:
                pass

    def _base_ydl_opts(self) -> Dict[str, Any]:
        """Shared yt-dlp defaults for metadata extraction paths."""
        return {
            'retries': 10,
            'fragment_retries': 10,
            'extractor_retries': 5,
            'file_access_retries': 3,
            'concurrent_fragment_downloads': 1,
            'http_chunk_size': 10 * 1024 * 1024,
        }

    def _yt_dlp_base_command(self) -> List[str]:
        """Return preferred yt-dlp command form (binary or module fallback)."""
        yt_dlp_bin = shutil.which('yt-dlp')
        if yt_dlp_bin:
            return [yt_dlp_bin]
        return [sys.executable, '-m', 'yt_dlp']

    def _emit_stage(self, progress_hook: Optional[Callable], stage: str):
        if progress_hook:
            progress_hook({'status': 'stage', 'stage': stage})

    def has_ffmpeg(self) -> bool:
        """Check ffmpeg availability for merge workflows."""
        return bool(shutil.which('ffmpeg'))

    def extract_info(self, url: str):
        """Extract video/playlist info without downloading."""
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
        }
        ydl_opts.update(self._base_ydl_opts())

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def get_available_video_formats(self, url: str) -> Dict[str, Any]:
        """
        Fetch and parse available formats using `yt-dlp --list-formats URL`.

        This output is treated as the source of truth for stream availability.
        """
        if not url or not url.strip():
            return {'video_formats': [], 'error': 'Please enter a YouTube URL'}

        if not self._is_valid_url(url):
            return {'video_formats': [], 'error': 'Invalid URL'}

        try:
            command = self._yt_dlp_base_command() + ['--list-formats', url]
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                creationflags=creationflags,
                timeout=120,
            )

            output = f"{result.stdout}\n{result.stderr}".strip()
            if result.returncode != 0:
                raise FormatDiscoveryError(output or 'yt-dlp failed to list formats')

            all_formats = self.parse_list_formats_output(result.stdout)
            if not all_formats:
                raise FormatDiscoveryError('No parseable formats found in yt-dlp output')

            quality_options = self.build_quality_options(all_formats)
            if not quality_options:
                raise NoCompatibleFormatError('No compatible video quality options were found')

            return {
                'video_formats': quality_options,
                'all_formats': all_formats,
                'error': None,
            }
        except DownloadPipelineError as exc:
            return {'video_formats': [], 'error': str(exc), 'error_code': exc.code}
        except subprocess.TimeoutExpired:
            return {'video_formats': [], 'error': 'Timed out while fetching formats'}
        except Exception as exc:
            return {'video_formats': [], 'error': str(exc)}

    def parse_list_formats_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse `yt-dlp --list-formats` table output into normalized stream entries."""
        parsed: List[Dict[str, Any]] = []
        lines = output.splitlines()

        seen_header = False
        for raw_line in lines:
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith('[info]'):
                continue
            if stripped.lower().startswith('format code'):
                continue
            if 'ID' in stripped and 'EXT' in stripped and 'RESOLUTION' in stripped:
                seen_header = True
                continue
            if not seen_header:
                continue
            if set(stripped) == {'-'}:
                continue

            parsed_line = self._parse_format_line(stripped)
            if parsed_line:
                parsed.append(parsed_line)

        return parsed

    def _parse_format_line(self, line: str) -> Optional[Dict[str, Any]]:
        if '|' in line:
            left, right = line.split('|', 1)
            notes = right.strip()
        else:
            left = line
            notes = ''

        tokens = left.split()
        if len(tokens) < 3:
            return None

        format_id = tokens[0].strip()
        ext = tokens[1].strip()
        left_rest = ' '.join(tokens[2:]).strip()
        lower_full = f"{left_rest} {notes}".lower()

        has_video = 'audio only' not in lower_full
        has_audio = 'video only' not in lower_full

        if not has_video and not has_audio:
            return None

        resolution = 'unknown'
        if 'audio only' in lower_full:
            resolution = 'audio only'
        else:
            match = self._HEIGHT_RE.search(left_rest)
            if match:
                if match.group('h1'):
                    # Preserve WxH string where possible.
                    wh_match = re.search(r'\d{2,5}x\d{2,5}', left_rest)
                    resolution = wh_match.group(0) if wh_match else f"{match.group('h1')}p"
                else:
                    resolution = f"{match.group('h2')}p"
            else:
                resolution = left_rest.split()[0] if left_rest else 'unknown'

        return {
            'format_id': format_id,
            'ext': ext,
            'resolution': resolution,
            'height': self._extract_height(resolution),
            'fps': self._extract_fps(left_rest + ' ' + notes),
            'has_video': has_video,
            'has_audio': has_audio,
            'category': self._classify_category(has_video, has_audio),
            'filesize': self._extract_size_bytes(notes),
            'tbr_kbps': self._extract_tbr(notes),
            'notes': notes,
            'raw': line,
        }

    def _classify_category(self, has_video: bool, has_audio: bool) -> str:
        if has_video and has_audio:
            return 'combined'
        if has_video and not has_audio:
            return 'video_only'
        return 'audio_only'

    def _extract_height(self, resolution: str) -> Optional[int]:
        if not resolution:
            return None
        match = self._HEIGHT_RE.search(resolution)
        if not match:
            return None
        if match.group('h1'):
            return int(match.group('h1'))
        return int(match.group('h2')) if match.group('h2') else None

    def _extract_fps(self, value: str) -> Optional[float]:
        match = self._FPS_RE.search(value)
        if not match:
            return None
        try:
            return float(match.group('fps'))
        except ValueError:
            return None

    def _extract_tbr(self, notes: str) -> Optional[float]:
        match = self._TBR_RE.search(notes)
        if not match:
            return None
        try:
            return float(match.group('tbr'))
        except ValueError:
            return None

    def _extract_size_bytes(self, notes: str) -> Optional[int]:
        match = self._SIZE_RE.search(notes)
        if not match:
            return None

        number = float(match.group('num'))
        unit = match.group('unit').upper()
        multiplier = {
            'KB': 1000,
            'MB': 1000 ** 2,
            'GB': 1000 ** 3,
            'TB': 1000 ** 4,
            'KIB': 1024,
            'MIB': 1024 ** 2,
            'GIB': 1024 ** 3,
            'TIB': 1024 ** 4,
        }.get(unit)
        if not multiplier:
            return None
        return int(number * multiplier)

    def build_quality_options(self, formats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create UI quality options grouped by resolution/height."""
        audio_candidates = [f for f in formats if f['category'] == 'audio_only']
        best_audio = max(audio_candidates, key=self._audio_score, default=None)

        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for fmt in formats:
            if fmt['category'] in ('combined', 'video_only') and fmt.get('height'):
                grouped.setdefault(int(fmt['height']), []).append(fmt)

        options: List[Dict[str, Any]] = []
        for height, candidates in grouped.items():
            best_video = max(candidates, key=self._video_score)
            requires_merge = best_video['category'] == 'video_only'
            audio_format_id = best_audio['format_id'] if requires_merge and best_audio else None

            label = self._build_quality_label(best_video, requires_merge)
            options.append({
                'format_id': best_video['format_id'],
                'height': height,
                'fps': best_video.get('fps'),
                'ext': best_video.get('ext'),
                'resolution': label,
                'filesize': best_video.get('filesize'),
                'has_audio': best_video.get('has_audio', False),
                'has_video': best_video.get('has_video', True),
                'is_combined': best_video['category'] == 'combined',
                'requires_merge': requires_merge,
                'audio_format_id': audio_format_id,
                'notes': best_video.get('notes', ''),
            })

        options.sort(key=lambda item: item.get('height') or 0, reverse=True)
        return options

    def _video_score(self, fmt: Dict[str, Any]) -> tuple:
        return (
            float(fmt.get('fps') or 0),
            float(fmt.get('tbr_kbps') or 0),
            int(fmt.get('filesize') or 0),
            1 if fmt['category'] == 'combined' else 0,
        )

    def _audio_score(self, fmt: Dict[str, Any]) -> tuple:
        return (
            float(fmt.get('tbr_kbps') or 0),
            int(fmt.get('filesize') or 0),
        )

    def _build_quality_label(self, fmt: Dict[str, Any], requires_merge: bool) -> str:
        parts = []
        height = fmt.get('height')
        if height:
            parts.append(f"{height}p")
        else:
            parts.append(str(fmt.get('resolution') or 'Unknown'))

        fps = fmt.get('fps')
        if fps and fps > 30:
            parts.append(f"{int(fps)}fps")

        ext = fmt.get('ext')
        if ext:
            parts.append(f"({str(ext).upper()})")

        if fmt.get('filesize'):
            size = fmt['filesize']
            if size >= 1024 ** 3:
                parts.append(f"~{size / (1024 ** 3):.1f}GB")
            elif size >= 1024 ** 2:
                parts.append(f"~{size / (1024 ** 2):.0f}MB")

        parts.append('- requires audio merge' if requires_merge else '- ready to download directly')
        return ' '.join(parts)

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL to reduce malformed/unsafe input handling."""
        if not url or not isinstance(url, str):
            return False

        try:
            parsed = urllib.parse.urlparse(url.strip())
            if parsed.scheme not in ('http', 'https'):
                return False
            if not parsed.netloc:
                return False

            hostname = parsed.hostname.lower() if parsed.hostname else ''
            blocked_hosts = ['localhost', '127.0.0.1', '0.0.0.0', '::1']
            if hostname in blocked_hosts:
                return False

            if hostname.startswith((
                '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', '172.21.',
                '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
                '172.29.', '172.30.', '172.31.', '192.168.'
            )):
                return False

            return True
        except Exception:
            return False

    def estimate_size(self, url: str, item_type: str, quality: str, audio_format: str) -> Optional[int]:
        """Estimate total download size in bytes (best-effort)."""
        try:
            import yt_dlp

            ydl_opts = {'quiet': True, 'no_warnings': True}
            ydl_opts.update(self._base_ydl_opts())

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if 'entries' in info:
                    total_size = 0
                    for entry in info['entries']:
                        if entry:
                            size = self._estimate_single_size(entry, item_type, quality)
                            if size:
                                total_size += size
                    return total_size if total_size > 0 else None
                return self._estimate_single_size(info, item_type, quality)
        except Exception:
            return None

    def _estimate_single_size(self, info: dict, item_type: str, quality: str) -> Optional[int]:
        if item_type == 'audio':
            for fmt in info.get('formats', []):
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    if size:
                        return int(size)
            return None

        for fmt in info.get('formats', []):
            if fmt.get('format_id') == quality:
                size = fmt.get('filesize') or fmt.get('filesize_approx')
                if size:
                    return int(size)
        return None

    def _build_download_plan(self, item) -> DownloadPlan:
        if item.item_type == 'audio':
            return DownloadPlan(mode='audio', selector='bestaudio/best', needs_merge=False)

        selected_video = (item.quality or '').strip()
        selected_audio = getattr(item, 'selected_audio_format_id', None)
        requires_merge = bool(getattr(item, 'requires_merge', False))
        selected_height = getattr(item, 'height', None)

        def _fallback_selector_for_height(height_value: Optional[int]) -> str:
            if height_value:
                height = int(height_value)
                return (
                    f"best[height={height}][ext=mp4]/best[height={height}]"
                    f"/best[height>={height}][ext=mp4]/best[height>={height}]"
                    f"/best[height<={height}][ext=mp4]/best[height<={height}]"
                    f"/best[ext=mp4]/best"
                )
            return 'best[ext=mp4]/best'

        # Rule A/B for explicit format selection from listed formats.
        if selected_video:
            if requires_merge:
                if not selected_audio:
                    raise NoCompatibleFormatError('No compatible audio-only stream found for this quality')
                return DownloadPlan(
                    mode='merge',
                    selector=f"{selected_video}+{selected_audio}/{_fallback_selector_for_height(selected_height)}",
                    needs_merge=True,
                    video_format_id=selected_video,
                    audio_format_id=selected_audio,
                )
            return DownloadPlan(
                mode='direct',
                selector=f"{selected_video}/{_fallback_selector_for_height(selected_height)}",
                needs_merge=False,
                video_format_id=selected_video,
            )

        # Rule C automatic capped-quality mode (playlist/fallback mode).
        if getattr(item, 'height', None):
            height = int(item.height)
            return DownloadPlan(
                mode='auto',
                selector=(
                    f"best[height<={height}][ext=mp4]/best[height<={height}]"
                    f"/best[height>={height}][ext=mp4]/best[height>={height}]"
                    f"/best[ext=mp4]/best"
                ),
                needs_merge=False,
            )

        return DownloadPlan(mode='auto', selector='bestvideo+bestaudio/best', needs_merge=True)

    def download_item(self, item, folder: str, progress_hook: Callable, should_cancel: Optional[Callable[[], bool]] = None):
        """Download a single item using explicit yt-dlp command execution."""
        folder = os.path.abspath(folder)
        if not os.path.isdir(folder):
            raise ValueError(f"Invalid download folder: {folder}")

        if should_cancel and should_cancel():
            raise DownloadCancelledError()

        plan = self._build_download_plan(item)

        if item.is_playlist and item.merge_playlist and not self.has_ffmpeg():
            raise MissingFFmpegError('FFmpeg was not found. Install FFmpeg to merge playlist files.')

        if plan.needs_merge and not self.has_ffmpeg():
            raise MissingFFmpegError('FFmpeg was not found. Install FFmpeg to download merge-required qualities.')

        self._emit_stage(progress_hook, 'downloading selected quality')
        if plan.needs_merge:
            self._emit_stage(progress_hook, 'downloading video stream')

        temp_folder = None
        outtmpl = os.path.join(folder, '%(title).200s.%(ext)s')
        before_files = self._snapshot_files(folder)

        if item.is_playlist and item.merge_playlist:
            temp_folder = tempfile.mkdtemp(prefix='ytdl_playlist_', dir=folder)
            outtmpl = os.path.join(temp_folder, '%(playlist_index)03d - %(title).150s.%(ext)s')

        cmd = self._yt_dlp_base_command() + [
            '--retries', '10',
            '--fragment-retries', '10',
            '--extractor-retries', '5',
            '--file-access-retries', '3',
            '-f', plan.selector,
            '-o', outtmpl,
        ]

        if item.item_type == 'audio':
            cmd.extend(['-x', '--audio-format', 'mp3', '--audio-quality', str(item.audio_format or '192')])
        elif plan.needs_merge:
            cmd.extend(['--merge-output-format', 'mp4'])

        if item.item_type == 'video' and item.is_playlist and item.merge_playlist:
            # Keep playlist segments in MP4 so concat merge can process them consistently.
            cmd.extend(['--remux-video', 'mp4'])

        playlist_items = (getattr(item, 'playlist_items', None) or '').strip()
        if item.is_playlist and playlist_items:
            cmd.extend(['--playlist-items', playlist_items])

        cmd.append(item.url)

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )

        captured_lines: List[str] = []
        emitted_audio_stage = False
        emitted_merge_stage = False

        def _cancel_process_and_raise():
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            self._cleanup_cancelled_download(folder, before_files, temp_folder)
            raise DownloadCancelledError()

        for raw_line in process.stdout or []:
            if should_cancel and should_cancel():
                _cancel_process_and_raise()

            line = raw_line.strip()
            if not line:
                continue
            captured_lines.append(line)

            lower_line = line.lower()
            if plan.needs_merge and not emitted_audio_stage and 'audio' in lower_line and 'destination' in lower_line:
                emitted_audio_stage = True
                self._emit_stage(progress_hook, 'downloading audio stream')

            if plan.needs_merge and not emitted_merge_stage and (
                '[merger]' in lower_line or 'merging formats into' in lower_line
            ):
                emitted_merge_stage = True
                self._emit_stage(progress_hook, 'merging streams')

            if '[download]' in line:
                progress_payload: Dict[str, Any] = {'status': 'downloading'}
                percent_match = self._DOWNLOAD_PERCENT_RE.search(line)
                speed_match = self._DOWNLOAD_SPEED_RE.search(line)
                eta_match = self._DOWNLOAD_ETA_RE.search(line)

                if percent_match:
                    progress_payload['percent'] = float(percent_match.group('pct'))
                if speed_match:
                    progress_payload['speed_text'] = speed_match.group('speed')
                if eta_match:
                    progress_payload['eta_text'] = eta_match.group('eta')

                progress_hook(progress_payload)

        process.wait()

        if should_cancel and should_cancel():
            self._cleanup_cancelled_download(folder, before_files, temp_folder)
            raise DownloadCancelledError()

        output_text = '\n'.join(captured_lines)

        if process.returncode != 0:
            self._raise_download_failure(output_text, plan)

        if item.is_playlist and item.merge_playlist and temp_folder:
            ext = 'mp3' if item.item_type == 'audio' else 'mp4'
            output_name = sanitize_filename(item.custom_name if item.custom_name else item.title)
            output_file = os.path.join(folder, f"{output_name}.{ext}")

            self._emit_stage(progress_hook, 'merging streams')
            success = merge_playlist_files(temp_folder, output_file, ext)
            if success and os.path.exists(temp_folder):
                try:
                    shutil.rmtree(temp_folder)
                except Exception:
                    pass

            if not success:
                raise MergeFailureError('Failed to merge playlist files')

        self._emit_stage(progress_hook, 'completed')
        progress_hook({'status': 'finished'})
        return True

    def _raise_download_failure(self, output: str, plan: DownloadPlan):
        lower = output.lower()

        if 'ffmpeg' in lower and ('not found' in lower or 'not installed' in lower or 'ffprobe and ffmpeg not found' in lower):
            raise MissingFFmpegError('FFmpeg is missing. Install FFmpeg and retry merge-required downloads.')

        if 'requested format is not available' in lower or 'no video formats found' in lower:
            raise NoCompatibleFormatError('Requested format is no longer available for this video')

        if plan.needs_merge and ('[merger]' in lower or 'unable to merge' in lower):
            raise MergeFailureError('Download completed but merging streams failed')

        if plan.needs_merge:
            raise MergeFailureError('Merged download failed')
        raise DirectDownloadError('Direct download failed')


def merge_playlist_files(temp_folder: str, output_file: str, ext: str) -> bool:
    """Merge all downloaded files into one using FFmpeg."""
    try:
        temp_folder = os.path.abspath(temp_folder)
        if not os.path.isdir(temp_folder):
            raise ValueError(f"Invalid temp folder: {temp_folder}")

        output_file = os.path.abspath(output_file)
        patterns = ['*.mp3'] if ext == 'mp3' else ['*.mp4']

        files = []
        for pattern in patterns:
            files.extend(glob.glob(os.path.join(temp_folder, pattern)))
        files.sort()

        if not files:
            raise RuntimeError('No files found to merge')

        for file_path in files:
            file_abs = os.path.abspath(file_path)
            if not file_abs.startswith(temp_folder):
                raise ValueError(f"Invalid file path detected: {file_path}")

        list_file = os.path.join(temp_folder, 'filelist.txt')
        with open(list_file, 'w', encoding='utf-8') as file_handle:
            for file_path in files:
                safe_path = file_path.replace('\\', '/').replace("'", "'\\''")
                file_handle.write(f"file '{safe_path}'\n")

        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            raise RuntimeError('FFmpeg not found. Please install FFmpeg and add it to PATH.')

        ffmpeg_cmd = [
            ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
            '-i', list_file, '-c', 'copy', output_file,
        ]

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=3600,
        )

        if result.returncode != 0:
            if ext == 'mp3':
                ffmpeg_cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
                    '-acodec', 'libmp3lame', '-b:a', '192k', output_file,
                ]
            else:
                ffmpeg_cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
                    '-c:v', 'libx264', '-c:a', 'aac', '-preset', 'fast', output_file,
                ]

            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                creationflags=creationflags,
                timeout=7200,
            )
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {result.stderr}")

        return True
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False

