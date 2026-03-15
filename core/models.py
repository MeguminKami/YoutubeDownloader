"""Data models for the application."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class QualityOption:
    """UI-facing quality option derived from `yt-dlp --list-formats` output."""
    format_id: str
    label: str
    height: Optional[int]
    ext: str
    fps: Optional[float]
    has_audio: bool
    has_video: bool
    requires_merge: bool
    audio_format_id: Optional[str] = None
    notes: str = ""


@dataclass
class DownloadPlan:
    """Concrete yt-dlp execution plan resolved before download starts."""
    mode: str  # direct, merge, auto, audio
    selector: str
    needs_merge: bool
    video_format_id: Optional[str] = None
    audio_format_id: Optional[str] = None

@dataclass
class DownloadItem:
    """Represents a single download item in the queue"""
    url: str
    item_type: str = "video"  # "video" or "audio"
    quality: Optional[str] = None  # Stores format_id for video downloads (critical for correct download)
    audio_format: Optional[str] = None
    is_playlist: bool = False
    merge_playlist: bool = False
    custom_name: Optional[str] = None
    title: str = "Loading..."
    status: str = "Pending"
    estimated_size: Optional[int] = None  # in bytes
    quality_label: Optional[str] = None  # Human-readable quality label (e.g., "1080p 60fps (MP4)")
    height: Optional[int] = None  # Video height for fallback format selection
    requires_merge: bool = False
    selected_audio_format_id: Optional[str] = None
    selected_video_format_id: Optional[str] = None
