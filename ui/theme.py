"""Theme management for light/dark modes"""
import customtkinter as ctk
from dataclasses import dataclass

@dataclass
class ColorScheme:
    bg: str
    surface: str
    hover: str
    accent_blue: str
    accent_purple: str
    text_primary: str
    text_secondary: str
    text_tertiary: str

class ThemeManager:
    DARK = ColorScheme(
        bg="#1a1f2e", surface="#252b42", hover="#2f3654",
        accent_blue="#2dd4ff", accent_purple="#7c5cff",
        text_primary="#ffffff", text_secondary="#b8c1ec", text_tertiary="#6b7794"
    )

    LIGHT = ColorScheme(
        bg="#f0f2f5", surface="#ffffff", hover="#e8eaf0",
        accent_blue="#0ea5e9", accent_purple="#8b5cf6",
        text_primary="#1a1f2e", text_secondary="#4b5563", text_tertiary="#9ca3af"
    )

    def __init__(self):
        self.current_theme = "dark"
        self._callbacks = []

    def get_colors(self) -> ColorScheme:
        return self.DARK if self.current_theme == "dark" else self.LIGHT

    def toggle(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        ctk.set_appearance_mode(self.current_theme)
        for callback in self._callbacks:
            callback(self.get_colors())

    def register_callback(self, callback):
        self._callbacks.append(callback)

    def is_dark(self) -> bool:
        return self.current_theme == "dark"
