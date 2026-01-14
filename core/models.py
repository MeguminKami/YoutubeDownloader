"""
Data models for the application
"""
from dataclasses import dataclass
from typing import Optional

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
