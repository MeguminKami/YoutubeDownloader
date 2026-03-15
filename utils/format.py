"""
Formatting utilities for bytes, speed, ETA, etc.
"""
from typing import Optional

def _to_non_negative_number(value: Optional[float]) -> float:
    """Convert possibly-missing numeric values to a safe non-negative float."""
    if value is None:
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if numeric > 0 else 0.0


def format_bytes(bytes_val: Optional[float]) -> str:
    """Format bytes to human-readable format"""
    bytes_val = _to_non_negative_number(bytes_val)
    if bytes_val >= 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"
    elif bytes_val >= 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val:.0f} B"

def format_speed(speed_bytes: Optional[float]) -> str:
    """Format speed in bytes/sec to human-readable format"""
    speed_bytes = _to_non_negative_number(speed_bytes)
    if speed_bytes <= 0:
        return "--"
    if speed_bytes >= 1024 * 1024:
        return f"{speed_bytes / (1024 * 1024):.1f} MB/s"
    elif speed_bytes >= 1024:
        return f"{speed_bytes / 1024:.1f} KB/s"
    else:
        return f"{speed_bytes:.0f} B/s"

def format_eta(eta_seconds: Optional[float]) -> str:
    """Format ETA in seconds to human-readable format"""
    eta_seconds = _to_non_negative_number(eta_seconds)
    if eta_seconds <= 0:
        return "--"

    eta_seconds = int(eta_seconds)
    if eta_seconds >= 3600:
        return f"{eta_seconds // 3600}h {(eta_seconds % 3600) // 60}m"
    elif eta_seconds >= 60:
        return f"{eta_seconds // 60}m {eta_seconds % 60}s"
    else:
        return f"{eta_seconds}s"

class SpeedSmoother:
    """
    Exponential moving average for smoothing download speeds
    """
    def __init__(self, alpha=0.3):
        self.alpha = alpha
        self.smoothed_speed = None

    def update(self, new_speed: float) -> float:
        """Update with new speed value and return smoothed speed"""
        if self.smoothed_speed is None:
            self.smoothed_speed = new_speed
        else:
            self.smoothed_speed = self.alpha * new_speed + (1 - self.alpha) * self.smoothed_speed
        return self.smoothed_speed

    def reset(self):
        """Reset the smoother"""
        self.smoothed_speed = None