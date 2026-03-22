"""Theme management for light and dark modes."""
from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk

from utils.config_store import load_ui_state, save_ui_state


@dataclass(frozen=True)
class ColorScheme:
    bg: str
    hero_bg: str
    surface: str
    surface_alt: str
    surface_soft: str
    input_bg: str
    primary: str
    primary_hover: str
    primary_fg: str
    secondary: str
    secondary_hover: str
    success: str
    warning: str
    danger: str
    text_primary: str
    text_secondary: str
    text_muted: str
    border: str
    divider: str
    pill_bg: str
    pill_border: str
    tab_active: str
    shadow: str


class ThemeManager:
    """Keeps theme state and notifies UI consumers."""

    DARK = ColorScheme(
        bg="#09090B",
        hero_bg="#121215",
        surface="#101114",
        surface_alt="#17181C",
        surface_soft="#0D0E12",
        input_bg="#14161B",
        primary="#FF0000",
        primary_hover="#D90404",
        primary_fg="#FFFFFF",
        secondary="#24262C",
        secondary_hover="#2F323A",
        success="#22C55E",
        warning="#FBBF24",
        danger="#EF4444",
        text_primary="#F7F8FA",
        text_secondary="#C2C6D0",
        text_muted="#8E95A3",
        border="#262932",
        divider="#1C1F27",
        pill_bg="#250D0D",
        pill_border="#4F1B1B",
        tab_active="#16181E",
        shadow="#030303",
    )

    LIGHT = ColorScheme(
        bg="#F8F8FA",
        hero_bg="#FFF5F5",
        surface="#FFFFFF",
        surface_alt="#F4F5F7",
        surface_soft="#EEF0F3",
        input_bg="#FFFFFF",
        primary="#FF0000",
        primary_hover="#D90404",
        primary_fg="#FFFFFF",
        secondary="#ECEEF2",
        secondary_hover="#E1E5EB",
        success="#16A34A",
        warning="#D97706",
        danger="#DC2626",
        text_primary="#111318",
        text_secondary="#4A5568",
        text_muted="#6B7280",
        border="#E3E7EE",
        divider="#E9ECF2",
        pill_bg="#FFF0F0",
        pill_border="#FFD4D4",
        tab_active="#FFFFFF",
        shadow="#D4D8DF",
    )

    def __init__(self):
        state = load_ui_state()
        saved_theme = state.get("theme", "dark")
        self.current_theme = saved_theme if saved_theme in {"dark", "light"} else "dark"
        self._callbacks = []
        ctk.set_appearance_mode(self.current_theme)

    def get_colors(self) -> ColorScheme:
        return self.DARK if self.current_theme == "dark" else self.LIGHT

    def set_theme(self, theme_name: str):
        if theme_name not in {"dark", "light"}:
            return
        if theme_name == self.current_theme:
            return

        self.current_theme = theme_name
        ctk.set_appearance_mode(self.current_theme)
        save_ui_state({"theme": self.current_theme})

        for callback in self._callbacks:
            callback(self.get_colors())

    def toggle(self):
        self.set_theme("light" if self.current_theme == "dark" else "dark")

    def register_callback(self, callback):
        self._callbacks.append(callback)

    def is_dark(self) -> bool:
        return self.current_theme == "dark"
