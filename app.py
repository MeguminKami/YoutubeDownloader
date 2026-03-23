"""Main application class."""
from __future__ import annotations

import copy
import os
import re
import threading
import webbrowser
from datetime import datetime
from tkinter import TclError, filedialog, messagebox
from typing import Callable, Iterable, List, Optional, Sequence

import customtkinter as ctk

from core.auth import CookieManager
from core.deps import check_yt_dlp, get_missing_bundled_tools, is_frozen_runtime
from core.downloader import (
    DirectDownloadError,
    DownloadCancelledError,
    Downloader,
    MergeFailureError,
    MissingFFmpegError,
    NoCompatibleFormatError,
)
from core.models import DownloadItem
from ui.dialogs import InstallerDialog, OptionsDialog, ProgressDialog, CookieInputDialog
from ui.theme import ThemeManager
from ui.visual_assets import VisualAssets
from utils.format import format_bytes, format_eta, format_speed, SpeedSmoother
from utils.history_store import load_history_items, save_history_items
from utils.media import resolve_thumbnail_url
from utils.thumbnail_cache import ThumbnailCacheManager


def _ellipsize(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return ""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds_left = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds_left:02d}"
    return f"{minutes}:{seconds_left:02d}"


def _format_timestamp(value: Optional[datetime]) -> str:
    if not value:
        return "Just now"
    return value.strftime("%b %d, %H:%M")


QUEUE_THUMB_SIZE = (112, 63)
HISTORY_THUMB_SIZE = (96, 54)
PROGRESS_THUMB_SIZE = (96, 54)
COOKIE_PROBE_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class YoutubeGrabApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("YoutubeGrab")
        self.geometry("1180x860")
        self.minsize(940, 680)

        self.theme_manager = ThemeManager()
        self.theme_manager.register_callback(self._on_theme_change)
        self.cookie_manager = CookieManager()

        ctk.set_default_color_theme("blue")

        self.download_queue: List[DownloadItem] = []
        self.download_history: List[DownloadItem] = []
        self.yt_dlp_available = False
        self.cookies_validated = False
        self.cookies_validation_in_progress = False
        self._download_active = False
        self._processing_url = False
        self._cancel_requested = False
        self._session_created_files = set()
        self._download_folder = None
        self._window_icon = None
        self._window_icon_ico = None
        self._pending_url_focus_after_id = None
        self.progress_dialog = None
        self.active_tab = "queue"
        self.thumbnail_cache = ThumbnailCacheManager(os.path.dirname(os.path.abspath(__file__)))
        self._thumbnail_fetching = set()
        self._load_history()

        self._apply_theme()
        self._load_brand_assets()
        self.create_widgets()

        self.after(100, self._check_dependencies)

    def _apply_theme(self):
        self.colors = self.theme_manager.get_colors()
        self.visuals = VisualAssets(self.colors)
        self.configure(fg_color=self.colors.bg)

    def _load_brand_assets(self):
        """Create the application logo and window icon from programmatic assets."""
        try:
            self._brand_logo_image = self.visuals.brand_mark(52)
        except Exception:
            self._brand_logo_image = None

        try:
            self._window_icon = self.visuals.brand_photoimage(64)
            self.iconphoto(True, self._window_icon)
        except Exception:
            self._window_icon = None

        try:
            ico_path = self.visuals.save_brand_ico()
            if ico_path:
                self._window_icon_ico = ico_path
                self.iconbitmap(self._window_icon_ico)
        except Exception:
            self._window_icon_ico = None

    def _on_theme_change(self, _colors):
        """Recreate the UI with the new theme while preserving main screen state."""
        saved_url = ""
        if hasattr(self, "url_entry") and self.url_entry.winfo_exists():
            saved_url = self.url_entry.get().strip()

        saved_tab = getattr(self, "active_tab", "queue")

        # CustomTkinter may queue a focus restore to the previously-focused native
        # widget while the window appearance is changing on Windows.
        if hasattr(self, "focused_widget_before_withdraw"):
            self.focused_widget_before_withdraw = None
        if hasattr(self, "focused_widget_before_widthdraw"):
            self.focused_widget_before_widthdraw = None

        if self._pending_url_focus_after_id is not None:
            try:
                self.after_cancel(self._pending_url_focus_after_id)
            except TclError:
                pass
            self._pending_url_focus_after_id = None

        self._apply_theme()
        self._load_brand_assets()

        for widget in self.winfo_children():
            widget.destroy()

        self.create_widgets(initial_url=saved_url, initial_tab=saved_tab)
        self._update_auth_button()
        self.update_queue_display()
        self.update_history_display()

    def _focus_url_entry_safe(self):
        """Restore focus only if the current entry widget still exists."""
        if not self.winfo_exists():
            return

        if self._pending_url_focus_after_id is not None:
            try:
                self.after_cancel(self._pending_url_focus_after_id)
            except TclError:
                pass
            self._pending_url_focus_after_id = None

        def apply_focus():
            self._pending_url_focus_after_id = None
            try:
                if hasattr(self, "url_entry") and self.url_entry.winfo_exists():
                    self.url_entry.focus_set()
            except TclError:
                pass

        self._pending_url_focus_after_id = self.after_idle(apply_focus)

    def create_widgets(self, initial_url: str = "", initial_tab: str = "queue"):
        """Create the application UI."""
        self.active_tab = initial_tab if initial_tab in {"queue", "history"} else "queue"

        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=22, pady=18)

        self._build_navbar(root)
        self.workflow_shell = ctk.CTkFrame(
            root,
            fg_color=self.colors.surface,
            corner_radius=28,
            border_width=1,
            border_color=self.colors.border,
        )
        self.workflow_shell.pack(fill="both", expand=True)

        self._build_hero(self.workflow_shell)
        self._build_content(self.workflow_shell)

        if initial_url:
            self.url_entry.insert(0, initial_url)

        self._sync_url_controls()
        self.switch_tab(self.active_tab, force=True)
        self.update_queue_display()
        self.update_history_display()
        self._update_auth_button()
        self._set_url_feedback("", tone="muted")

    def _build_navbar(self, parent):
        nav = ctk.CTkFrame(
            parent,
            fg_color=self.colors.surface,
            corner_radius=20,
            border_width=1,
            border_color=self.colors.border,
            height=66,
        )
        nav.pack(fill="x", pady=(0, 18))
        nav.pack_propagate(False)

        brand_wrap = ctk.CTkFrame(nav, fg_color="transparent")
        brand_wrap.pack(side="left", padx=18, pady=12)

        ctk.CTkLabel(
            brand_wrap,
            text="",
            image=self._brand_logo_image,
        ).pack(side="left", padx=(0, 12))

        brand_text = ctk.CTkFrame(brand_wrap, fg_color="transparent")
        brand_text.pack(side="left")

        top = ctk.CTkFrame(brand_text, fg_color="transparent")
        top.pack(anchor="w")

        ctk.CTkLabel(
            top,
            text="YT",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.colors.text_primary,
        ).pack(side="left")

        ctk.CTkLabel(
            top,
            text="Grab",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.colors.primary,
        ).pack(side="left")

        ctk.CTkLabel(
            brand_text,
            text="Download video or audio with a cleaner queue workflow.",
            font=ctk.CTkFont(size=11),
            text_color=self.colors.text_muted,
        ).pack(anchor="w", pady=(1, 0))

        controls = ctk.CTkFrame(nav, fg_color="transparent")
        controls.pack(side="right", padx=16, pady=12)

        self.auth_button = ctk.CTkButton(
            controls,
            text="",
            width=144,
            height=38,
            corner_radius=14,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.show_cookie_help,
            compound="left",
        )
        self.auth_button.pack(side="left", padx=(0, 10))

        theme_icon = self.visuals.icon(
            "sun" if self.theme_manager.is_dark() else "moon",
            18,
            self.colors.warning if self.theme_manager.is_dark() else self.colors.text_primary,
        )
        self.theme_button = ctk.CTkButton(
            controls,
            text="",
            image=theme_icon,
            width=38,
            height=38,
            corner_radius=14,
            fg_color=self.colors.surface_alt,
            hover_color=self.colors.secondary_hover,
            border_width=1,
            border_color=self.colors.border,
            command=self._toggle_theme,
        )
        self.theme_button.pack(side="left")

    def _build_hero(self, parent):
        hero = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        hero.pack(fill="x", padx=24, pady=(22, 12))

        inner = ctk.CTkFrame(hero, fg_color="transparent")
        inner.pack(fill="x")

        ctk.CTkLabel(
            inner,
            text= "Paste a YouTube link below, then click Queue to choose format and quality.",
            font=ctk.CTkFont(size=13),
            text_color=self.colors.text_secondary,
            anchor="center",
            justify="center",
            wraplength=760,
        ).pack(anchor="center", pady=(0, 12))

        input_row = ctk.CTkFrame(inner, fg_color="transparent")
        input_row.pack(fill="x")
        input_row.grid_columnconfigure(0, weight=1)

        self.entry_shell = ctk.CTkFrame(
            input_row,
            fg_color=self.colors.input_bg,
            corner_radius=18,
            border_width=1,
            border_color=self.colors.border,
            height=54,
        )
        self.entry_shell.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.entry_shell.grid_columnconfigure(0, weight=1)
        self.entry_shell.grid_propagate(False)

        self.url_entry = ctk.CTkEntry(
            self.entry_shell,
            placeholder_text="https://youtube.com/watch?v=...",
            border_width=0,
            fg_color="transparent",
            height=50,
            font=ctk.CTkFont(size=14),
            text_color=self.colors.text_primary,
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(16, 0), pady=2)
        self.url_entry.bind("<KeyRelease>", lambda _event: self._sync_url_controls())
        self.url_entry.bind("<Return>", lambda _event: self.add_to_queue())

        self.url_action_button = ctk.CTkButton(
            self.entry_shell,
            text="Paste",
            image=self.visuals.icon("paste", 14, self.colors.text_secondary),
            compound="left",
            width=76,
            height=32,
            corner_radius=12,
            fg_color=self.colors.surface_alt,
            hover_color=self.colors.secondary_hover,
            text_color=self.colors.text_secondary,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.paste_url,
        )
        self.url_action_button.grid(row=0, column=1, sticky="e", padx=(8, 12), pady=11)

        self.fetch_button = ctk.CTkButton(
            input_row,
            text="Queue",
            image=self.visuals.icon("download", 16, self.colors.primary_fg),
            compound="left",
            width=150,
            height=54,
            corner_radius=18,
            fg_color=self.colors.primary,
            hover_color=self.colors.primary_hover,
            text_color=self.colors.primary_fg,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.add_to_queue,
        )
        self.fetch_button.grid(row=0, column=1, sticky="e")

        self.url_feedback = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=self.colors.text_muted,
        )
        self.url_feedback.pack(anchor="w", pady=(10, 0))

    def _build_content(self, parent):
        tabs_shell = ctk.CTkFrame(
            parent,
            fg_color="transparent",
        )
        tabs_shell.pack(fill="x", padx=24, pady=(0, 14))

        tabs_inner = ctk.CTkFrame(tabs_shell, fg_color="transparent")
        tabs_inner.pack(anchor="w")

        self.queue_tab_button = ctk.CTkButton(
            tabs_inner,
            text="Queue",
            image=self.visuals.icon("queue", 15, self.colors.text_primary),
            compound="left",
            height=38,
            corner_radius=14,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self.switch_tab("queue"),
        )
        self.queue_tab_button.pack(side="left", padx=(0, 8))

        self.history_tab_button = ctk.CTkButton(
            tabs_inner,
            text="History",
            image=self.visuals.icon("history", 15, self.colors.text_primary),
            compound="left",
            height=38,
            corner_radius=14,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self.switch_tab("history"),
        )
        self.history_tab_button.pack(side="left")

        self.panel_host = ctk.CTkFrame(parent, fg_color="transparent")
        self.panel_host.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        self.queue_panel = self._build_queue_panel(self.panel_host)
        self.history_panel = self._build_history_panel(self.panel_host)

    def _build_queue_panel(self, parent):
        panel = ctk.CTkFrame(
            parent,
            fg_color=self.colors.surface,
            corner_radius=24,
            border_width=1,
            border_color=self.colors.border,
        )
        panel.pack(fill="both", expand=True)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(20, 10))

        title_wrap = ctk.CTkFrame(header, fg_color="transparent")
        title_wrap.pack(side="left")

        ctk.CTkLabel(
            title_wrap,
            text="Download Queue",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors.text_primary,
        ).pack(anchor="w")

        self.queue_summary_label = ctk.CTkLabel(
            title_wrap,
            text="No items queued yet",
            font=ctk.CTkFont(size=12),
            text_color=self.colors.text_muted,
        )
        self.queue_summary_label.pack(anchor="w", pady=(3, 0))

        self.queue_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.queue_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self.queue_footer = ctk.CTkFrame(panel, fg_color="transparent")
        self.queue_footer.pack(fill="x", padx=22, pady=(0, 22))

        self.download_all_button = ctk.CTkButton(
            self.queue_footer,
            text="Download All",
            image=self.visuals.icon("download", 16, self.colors.primary_fg),
            compound="left",
            height=48,
            corner_radius=16,
            fg_color=self.colors.primary,
            hover_color=self.colors.primary_hover,
            text_color=self.colors.primary_fg,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_download,
        )
        self.download_all_button.pack(fill="x", expand=True)

        return panel

    def _build_history_panel(self, parent):
        panel = ctk.CTkFrame(
            parent,
            fg_color=self.colors.surface,
            corner_radius=24,
            border_width=1,
            border_color=self.colors.border,
        )

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.pack(fill="x", padx=22, pady=(20, 10))

        title_wrap = ctk.CTkFrame(header, fg_color="transparent")
        title_wrap.pack(side="left")

        ctk.CTkLabel(
            title_wrap,
            text="Download History",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors.text_primary,
        ).pack(anchor="w")

        self.history_summary_label = ctk.CTkLabel(
            title_wrap,
            text="Completed and failed jobs appear here during this session.",
            font=ctk.CTkFont(size=12),
            text_color=self.colors.text_muted,
        )
        self.history_summary_label.pack(anchor="w", pady=(3, 0))

        self.clear_failed_button = ctk.CTkButton(
            header,
            text="Clear Failed",
            image=self.visuals.icon("alert_circle", 16, self.colors.danger),
            compound="left",
            width=120,
            height=36,
            corner_radius=12,
            fg_color=self.colors.surface_alt,
            hover_color=self.colors.secondary_hover,
            text_color=self.colors.danger,
            border_width=1,
            border_color=self.colors.border,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.clear_failed_history,
        )
        self.clear_failed_button.pack(side="right", padx=(0, 8))

        self.clear_history_button = ctk.CTkButton(
            header,
            text="Clear All",
            image=self.visuals.icon("trash", 14, self.colors.danger),
            compound="left",
            width=110,
            height=34,
            corner_radius=12,
            fg_color=self.colors.surface_alt,
            hover_color=self.colors.secondary_hover,
            text_color=self.colors.danger,
            border_width=1,
            border_color=self.colors.border,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self.clear_history,
        )
        self.clear_history_button.pack(side="right")

        self.history_scroll = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True, padx=18, pady=(0, 22))

        return panel

    def _toggle_theme(self):
        if self._download_active or self._processing_url:
            messagebox.showinfo("Theme Locked", "Wait for the current action to finish before changing the theme.")
            return
        self.theme_manager.toggle()

    def _set_url_feedback(self, message: str, tone: str = "danger"):
        palette = {
            "danger": self.colors.danger,
            "success": self.colors.success,
            "muted": self.colors.text_muted,
        }
        self.url_feedback.configure(text=message, text_color=palette.get(tone, self.colors.text_muted))

    def _sync_url_controls(self):
        has_text = bool(self.url_entry.get().strip()) if hasattr(self, "url_entry") else False
        if not hasattr(self, "url_action_button"):
            return

        if has_text:
            self.url_action_button.configure(
                text="Clear",
                image=self.visuals.icon("close", 13, self.colors.text_secondary),
                command=self.clear_url,
            )
        else:
            self.url_action_button.configure(
                text="Paste",
                image=self.visuals.icon("paste", 14, self.colors.text_secondary),
                command=self.paste_url,
            )

        if has_text and self.url_feedback.cget("text") == "Paste a YouTube watch, shorts, or playlist URL to begin.":
            self._set_url_feedback("", tone="muted")

    def switch_tab(self, tab_name: str, force: bool = False):
        if not force and tab_name == self.active_tab:
            return

        self.active_tab = tab_name

        if tab_name == "queue":
            if self.history_panel.winfo_manager():
                self.history_panel.pack_forget()
            if not self.queue_panel.winfo_manager():
                self.queue_panel.pack(fill="both", expand=True)
        else:
            if self.queue_panel.winfo_manager():
                self.queue_panel.pack_forget()
            if not self.history_panel.winfo_manager():
                self.history_panel.pack(fill="both", expand=True)

        active_fg = self.colors.tab_active
        inactive_fg = self.colors.surface_soft

        self.queue_tab_button.configure(
            fg_color=active_fg if tab_name == "queue" else inactive_fg,
            hover_color=self.colors.secondary_hover,
            text_color=self.colors.text_primary,
            border_width=1,
            border_color=self.colors.border,
        )
        self.history_tab_button.configure(
            fg_color=active_fg if tab_name == "history" else inactive_fg,
            hover_color=self.colors.secondary_hover,
            text_color=self.colors.text_primary,
            border_width=1,
            border_color=self.colors.border,
        )

    def _check_dependencies(self):
        """Check if yt-dlp is installed."""
        if is_frozen_runtime():
            missing_tools = get_missing_bundled_tools()
            if missing_tools:
                missing_text = ", ".join(missing_tools)
                messagebox.showerror(
                    "Packaging Error",
                    (
                        "This release bundle is missing required runtime tools:\n"
                        f"{missing_text}\n\n"
                        "Please download a complete release package."
                    ),
                )
                self.quit()
                return

            if not check_yt_dlp():
                messagebox.showerror(
                    "Packaging Error",
                    (
                        "This release bundle is incomplete or corrupted.\n"
                        "The bundled yt-dlp tool could not be resolved at runtime.\n\n"
                        "Please download a fresh release build."
                    ),
                )
                self.quit()
                return

            self.yt_dlp_available = True
            self._validate_cookies(show_popup_on_invalid=True)
            return

        if check_yt_dlp():
            self.yt_dlp_available = True
            self._validate_cookies(show_popup_on_invalid=True)
        else:
            self._show_installer()

    def _show_installer(self):
        """Show installer dialog."""
        if is_frozen_runtime():
            messagebox.showerror(
                "Packaging Error",
                "Runtime dependency installation is disabled in packaged builds. Please use a complete release bundle.",
            )
            self.quit()
            return

        def on_success():
            self.yt_dlp_available = True
            self._validate_cookies(show_popup_on_invalid=True)
            messagebox.showinfo("Success", "yt-dlp installed successfully.")

        def on_failure():
            messagebox.showerror(
                "Installation Failed",
                "Could not install yt-dlp.\n\nInstall it manually with:\npip install yt-dlp"
            )
            self.quit()

        InstallerDialog(self, self.colors, on_success, on_failure)

    def paste_url(self):
        """Paste a URL from the clipboard."""
        try:
            clipboard_content = self.clipboard_get()
        except Exception:
            clipboard_content = ""

        if clipboard_content:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, clipboard_content)
            self._set_url_feedback("", tone="muted")
            self._sync_url_controls()
            self._focus_url_entry_safe()

    def clear_url(self):
        self.url_entry.delete(0, "end")
        self._set_url_feedback("", tone="muted")
        self._sync_url_controls()
        self._focus_url_entry_safe()

    def show_cookie_help(self):
        """Show information about cookies.txt."""
        auth_status = self.cookie_manager.get_cookie_status()
        has_cookie_file = bool(auth_status.get("has_cookie_file"))

        if has_cookie_file and self.cookies_validated:
            response = messagebox.askyesno(
                "Cookie Status",
                (
                    "Cookies are loaded and working.\n\n"
                    f"Cookie file location:\n{self.cookie_manager.cookie_file}\n\n"
                    "Do you want to remove the current cookies?"
                ),
            )
            if response:
                self._remove_cookies()
            return

        # Show cookie input dialog
        def on_save_cookies(cookie_content: str):
            try:
                os.makedirs(os.path.dirname(self.cookie_manager.cookie_file), exist_ok=True)
                with open(self.cookie_manager.cookie_file, "w", encoding="utf-8") as f:
                    f.write(cookie_content)

                # Validate cookies immediately
                def _after_validation(validated: bool):
                    if validated:
                        messagebox.showinfo("Success", "Cookies saved and validated successfully!")
                    else:
                        messagebox.showwarning(
                            "Cookies Saved",
                            "Cookies were saved, but validation failed.\n\n"
                            "They may not work correctly with YouTube."
                        )

                self._validate_cookies(on_complete=_after_validation)
            except Exception as exc:
                messagebox.showerror("Error", f"Failed to save cookies: {exc}")

        CookieInputDialog(self, self.colors, on_save_cookies)

    def _remove_cookies(self):
        """Remove the cookies.txt file."""
        try:
            if os.path.exists(self.cookie_manager.cookie_file):
                os.remove(self.cookie_manager.cookie_file)
            self.cookies_validated = False
            self._update_auth_button()
            messagebox.showinfo("Cookies Removed", "The cookie file has been removed.")
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to remove cookies: {exc}")

    def _validate_cookies(self, show_popup_on_invalid: bool = False, on_complete: Optional[Callable[[bool], None]] = None):
        """Validate cookies by requiring a parseable yt-dlp list-formats response."""
        if not self.yt_dlp_available:
            self.cookies_validation_in_progress = False
            self.cookies_validated = False
            self._update_auth_button()
            if on_complete:
                on_complete(False)
            return

        if not os.path.exists(self.cookie_manager.cookie_file):
            self.cookies_validation_in_progress = False
            self.cookies_validated = False
            self._update_auth_button()
            if on_complete:
                on_complete(False)
            return

        self.cookies_validation_in_progress = True
        self._update_auth_button()

        def validate_in_thread():
            """Run validation in background thread."""
            try:
                downloader = Downloader(cookie_manager=self.cookie_manager)
                probe = downloader.probe_cookie_validity_with_list_formats(COOKIE_PROBE_URL)
                validated = bool(probe.get("valid"))
                error_message = probe.get("error") or "Cookie validation failed."
            except Exception as exc:
                validated = False
                error_message = str(exc) or "Cookie validation failed."

            self.after(
                0,
                lambda: self._on_cookies_validated(
                    validated,
                    show_popup_on_invalid=show_popup_on_invalid,
                    error_message=error_message,
                    on_complete=on_complete,
                ),
            )

        # Run validation in background to avoid blocking UI
        threading.Thread(target=validate_in_thread, daemon=True).start()

    def _on_cookies_validated(
        self,
        validated: bool,
        show_popup_on_invalid: bool = False,
        error_message: str = "",
        on_complete: Optional[Callable[[bool], None]] = None,
    ):
        """Called when cookie validation completes."""
        self.cookies_validation_in_progress = False
        self.cookies_validated = validated
        self._update_auth_button()

        if show_popup_on_invalid and not validated:
            if error_message:
                messagebox.showwarning("Cookie Validation", self._format_processing_error(error_message))
            self.show_cookie_help()

        if on_complete:
            on_complete(validated)

    def _update_auth_button(self):
        """Refresh the cookie status button styling."""
        # Orange while validating, green for validated cookies, red for missing/invalid.
        if self.cookies_validation_in_progress:
            text = "Loading Cookies"
            icon_name = "alert_circle"
            fg_color = "#D97706"  # Orange
            hover_color = "#D97706"
            text_color = "#111827"
            state = "disabled"
        elif self.cookies_validated:
            text = "Cookies OK"
            icon_name = "lock"
            fg_color = "#006400"  # Dark green
            hover_color = "#008000"  # Green
            text_color = "#FFFFFF"  # White text
            state = "normal"
        else:
            text = "Insert Cookies"
            icon_name = "alert_circle"
            fg_color = "#8B0000"  # Dark red
            hover_color = "#A52A2A"  # Brown-red
            text_color = "#FFFFFF"  # White text
            state = "normal"

        self.auth_button.configure(
            text=text,
            image=self.visuals.icon(icon_name, 15, text_color),
            fg_color=fg_color,
            hover_color=hover_color,
            text_color=text_color,
            border_width=0,
            state=state,
        )

    def is_valid_youtube_url(self, url: str) -> bool:
        """Simple validation for YouTube URLs (watch, short, playlist, shorts)."""
        if not url or not isinstance(url, str):
            return False

        pattern = re.compile(
            r"^(?:https?://)?(?:www\.)?(?:m\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)(?:/|$)",
            re.IGNORECASE,
        )
        return bool(pattern.search(url.strip()))

    def _split_sentences_per_line(self, text: str) -> str:
        """Return readable popup text with one sentence per line."""
        if not text:
            return "Unknown error."

        normalized = " ".join(str(text).replace("\r", " ").replace("\n", " ").split())
        normalized = re.sub(r"^ERROR:\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"(?<=[.!?])\s+", "\n", normalized)
        return normalized.strip() if normalized.strip() else "Unknown error."

    def _format_processing_error(self, raw_error: str) -> str:
        """Map common yt-dlp extraction failures to clear user instructions."""
        lower = (raw_error or "").lower()
        if "sign in to confirm you're not a bot" in lower:
            auth_status = self.cookie_manager.get_cookie_status()
            cookie_path = self.cookie_manager.cookie_file

            if not auth_status["authenticated"]:
                return "\n".join([
                    "YouTube asked for account verification (bot detection).",
                    "",
                    "To fix this, provide YouTube cookies:",
                    "",
                    "1. Install browser extension 'Get cookies.txt LOCALLY'",
                    "2. Open YouTube.com while logged in",
                    "3. Export cookies using the extension",
                    f"4. Save the file as: {cookie_path}",
                    "5. Click the cookie button to verify",
                    "",
                    "Then try downloading again.",
                ])

            return "\n".join([
                "YouTube is still detecting bot activity.",
                "",
                "Your cookies may be expired or invalid.",
                "",
                "Try refreshing your cookies:",
                "1. Open YouTube.com in your browser",
                "2. Log out and log in again",
                "3. Export fresh cookies",
                f"4. Replace the file at: {cookie_path}",
                "5. Try again",
            ])

        return self._split_sentences_per_line(raw_error)

    def _set_fetch_busy(self, busy: bool):
        self._processing_url = busy

        entry_state = "disabled" if busy else "normal"
        self.url_entry.configure(state=entry_state)
        self.url_action_button.configure(state=entry_state)

        if busy:
            self.fetch_button.configure(text="Loading...", image=None, state="disabled")
        else:
            self.fetch_button.configure(
                text="Queue",
                image=self.visuals.icon("download", 16, self.colors.primary_fg),
                state="disabled" if self._download_active else "normal",
            )

    def add_to_queue(self):
        """Validate the URL and open the options dialog."""
        if not self.yt_dlp_available:
            messagebox.showerror("Error", "yt-dlp is not installed.")
            return

        if self._download_active:
            messagebox.showinfo("Download Running", "Wait for the current batch to finish before adding more items.")
            return

        if not os.path.exists(self.cookie_manager.cookie_file):
            self.show_cookie_help()
            return

        url = self.url_entry.get().strip()
        if not url:
            self._set_url_feedback("Paste a YouTube watch, shorts, or playlist URL to begin.")
            self._focus_url_entry_safe()
            return

        if not self.is_valid_youtube_url(url):
            self._set_url_feedback("The pasted text is not a valid YouTube URL.")
            self._focus_url_entry_safe()
            return

        self._set_url_feedback("", tone="muted")
        self._set_fetch_busy(True)

        thread = threading.Thread(target=self.process_url, args=(url,))
        thread.daemon = True
        thread.start()

    def process_url(self, url: str):
        """Process URL and show the options dialog."""
        try:
            downloader = Downloader(cookie_manager=self.cookie_manager)
            probe = downloader.probe_cookie_validity_with_list_formats(url)
            if not probe.get("valid"):
                error_message = probe.get("error") or "Could not list formats for this URL."
                error_code = probe.get("error_code") or "format_discovery_failed"
                self.after(0, lambda msg=error_message, code=error_code: self._handle_queue_probe_failure(msg, code))
                return

            info = downloader.extract_info(url)
            self.after(0, lambda: self.show_options_dialog(url, info))
        except Exception as exc:
            formatted_error = self._format_processing_error(str(exc))
            self.after(0, lambda msg=formatted_error: messagebox.showerror("Error Processing URL", msg))
        finally:
            self.after(0, lambda: self._set_fetch_busy(False))

    def _handle_queue_probe_failure(self, raw_error: str, error_code: str):
        if error_code == "invalid_cookies":
            self.cookies_validated = False
            self._update_auth_button()
            self._set_url_feedback("Cookies look invalid. Please update them and try again.", tone="danger")
            messagebox.showwarning("Cookie Validation", self._format_processing_error(raw_error))
            self.show_cookie_help()
            return

        self._set_url_feedback("yt-dlp failed to fetch formats for this URL.", tone="danger")
        messagebox.showwarning("Format Discovery", self._format_processing_error(raw_error))

    def show_options_dialog(self, url: str, info: dict):
        """Show the download options dialog."""
        default_thumbnail_url = resolve_thumbnail_url(info)

        def callback(items: Sequence[DownloadItem]):
            if items:
                for item in items:
                    if not item.source_url:
                        item.source_url = item.url or url
                    if not item.thumbnail_url:
                        item.thumbnail_url = default_thumbnail_url
                    if item.thumbnail_url and not item.cached_thumbnail_path:
                        item.cached_thumbnail_path = self.thumbnail_cache.get_cached_path(item.thumbnail_url)
                    if not item.channel:
                        item.channel = info.get("uploader") or info.get("channel")
                    item.status = "queued"
                    self.download_queue.append(item)
                    self._ensure_item_thumbnail(item, self.update_queue_display)
                self.clear_url()
                self._set_url_feedback("Added to queue.", tone="success")
            self.update_queue_display()

        OptionsDialog(
            self,
            self.colors,
            url,
            info,
            callback,
            cookie_manager=self.cookie_manager,
            thumbnail_cache=self.thumbnail_cache,
        )

    def _clear_scroll_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _tag(self, parent, text: str, tone: str = "neutral", icon: Optional[str] = None):
        palette = {
            "neutral": (self.colors.surface_soft, self.colors.text_secondary),
            "primary": (self.colors.pill_bg, self.colors.primary),
            "success": (self.colors.surface_soft, self.colors.success),
            "danger": (self.colors.surface_soft, self.colors.danger),
        }
        fg_color, text_color = palette.get(tone, palette["neutral"])
        label = ctk.CTkLabel(
            parent,
            text=f" {text} ",
            image=self.visuals.icon(icon, 12, text_color) if icon else None,
            compound="left",
            fg_color=fg_color,
            corner_radius=999,
            text_color=text_color,
            font=ctk.CTkFont(size=10, weight="bold"),
            height=24,
            anchor="center",
        )
        label.pack(side="left", padx=(0, 6))
        return label

    def _thumbnail_image_for_item(self, item: DownloadItem, size, refresh_callback=None):
        cached_path = getattr(item, "cached_thumbnail_path", None)
        if cached_path and os.path.exists(cached_path):
            image = self.visuals.local_media_image(cached_path, size)
            if image:
                return image

        if getattr(item, "thumbnail_url", None):
            existing = self.thumbnail_cache.get_cached_path(item.thumbnail_url)
            if existing:
                item.cached_thumbnail_path = existing
                image = self.visuals.local_media_image(existing, size)
                if image:
                    return image

            self._ensure_item_thumbnail(item, refresh_callback)

        return self.visuals.media_tile(size, item.item_type)

    def _ensure_item_thumbnail(self, item: DownloadItem, refresh_callback=None):
        thumbnail_url = (getattr(item, "thumbnail_url", None) or "").strip()
        if not thumbnail_url:
            return

        existing = self.thumbnail_cache.get_cached_path(thumbnail_url)
        if existing:
            item.cached_thumbnail_path = existing
            return

        if thumbnail_url in self._thumbnail_fetching:
            return

        self._thumbnail_fetching.add(thumbnail_url)

        def worker():
            cached_path = self.thumbnail_cache.ensure_cached(thumbnail_url)

            def finish():
                self._thumbnail_fetching.discard(thumbnail_url)
                if cached_path:
                    item.cached_thumbnail_path = cached_path
                    if callable(refresh_callback):
                        refresh_callback()

            self.after(0, finish)

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()

    def _refresh_progress_current_thumbnail(self):
        if not self.progress_dialog or not hasattr(self, "current_item_index"):
            return
        if not (0 <= getattr(self, "current_item_index", -1) < len(self.download_queue)):
            return

        item = self.download_queue[self.current_item_index]
        image = self._thumbnail_image_for_item(item, PROGRESS_THUMB_SIZE, self._refresh_progress_current_thumbnail)
        self.progress_dialog.update_current_item(item, image)

    def update_queue_display(self):
        """Refresh the queue panel cards."""
        self._clear_scroll_frame(self.queue_scroll)

        queue_count = len(self.download_queue)
        queued_count = sum(1 for item in self.download_queue if item.status in {"queued", "downloading"})
        self.queue_summary_label.configure(
            text=f"{queue_count} item{'s' if queue_count != 1 else ''} in queue"
            if queue_count
            else "No items queued yet"
        )

        self.queue_tab_button.configure(text=f"Queue ({queue_count})")
        self.download_all_button.configure(
            state="normal" if queue_count and not self._processing_url and not self._download_active else "disabled"
        )

        if queue_count == 0:
            self._render_empty_state(
                self.queue_scroll,
                "queue",
                "No items in queue",
                "Paste a YouTube link above and send it through the download options dialog.",
            )
        else:
            for index, item in enumerate(self.download_queue):
                self._render_queue_item(index, item)

        if queued_count == 0 and self.download_queue:
            self.download_all_button.configure(state="disabled" if self._download_active else "normal")

    def _render_empty_state(self, parent, icon_name: str, title: str, subtitle: str):
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="both", expand=True, pady=42)

        ctk.CTkLabel(
            wrap,
            text="",
            image=self.visuals.empty_state_tile((66, 66), icon_name),
        ).pack(pady=(0, 14))

        ctk.CTkLabel(
            wrap,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors.text_primary,
        ).pack()

        ctk.CTkLabel(
            wrap,
            text=subtitle,
            font=ctk.CTkFont(size=12),
            text_color=self.colors.text_muted,
            wraplength=520,
            justify="center",
        ).pack(pady=(6, 0))

    def _render_queue_item(self, index: int, item: DownloadItem):
        card = ctk.CTkFrame(
            self.queue_scroll,
            fg_color=self.colors.surface_alt,
            corner_radius=18,
            border_width=1,
            border_color=self.colors.border,
        )
        card.pack(fill="x", pady=(0, 10))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=14)
        inner.grid_columnconfigure(1, weight=1)

        thumb = ctk.CTkLabel(
            inner,
            text="",
            image=self._thumbnail_image_for_item(item, QUEUE_THUMB_SIZE, self.update_queue_display),
        )
        thumb.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14))

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(
            info,
            text=_ellipsize(item.title or "Untitled", 92),
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors.text_primary,
            anchor="w",
            justify="left",
            wraplength=540,
        ).pack(anchor="w")

        meta_pieces = [piece for piece in [item.channel or "YouTube", _format_duration(item.duration_seconds)] if piece]
        ctk.CTkLabel(
            info,
            text="  ".join(meta_pieces),
            font=ctk.CTkFont(size=11),
            text_color=self.colors.text_muted,
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(3, 0))

        tags = ctk.CTkFrame(info, fg_color="transparent")
        tags.pack(anchor="w", pady=(8, 0))

        self._tag(tags, "MP4" if item.item_type == "video" else "MP3", icon="video" if item.item_type == "video" else "music")

        if item.item_type == "video":
            quality_text = item.quality_label or (f"{item.height}p" if item.height else "Auto")
            self._tag(tags, quality_text)
        else:
            audio_text = f"{item.audio_format or '192'} kbps"
            self._tag(tags, audio_text)

        if item.is_playlist:
            self._tag(tags, "Playlist", icon="queue")

        if item.estimated_size:
            self._tag(tags, format_bytes(item.estimated_size))

        side = ctk.CTkFrame(inner, fg_color="transparent")
        side.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(14, 0))

        status_text, tone = self._status_text(item.status)
        self._tag(side, status_text, tone=tone)

        remove_btn = ctk.CTkButton(
            side,
            text="",
            image=self.visuals.icon("close", 13, self.colors.text_secondary),
            width=30,
            height=30,
            corner_radius=12,
            fg_color=self.colors.surface_soft,
            hover_color=self.colors.secondary_hover,
            border_width=1,
            border_color=self.colors.border,
            command=lambda idx=index: self.remove_from_queue(idx),
            state="disabled" if self._download_active else "normal",
        )
        remove_btn.pack(pady=(10, 0))

    def _status_text(self, status: Optional[str]):
        normalized = (status or "queued").lower()
        mapping = {
            "queued": ("Queued", "neutral"),
            "downloading": ("Downloading", "primary"),
            "completed": ("Completed", "success"),
            "failed": ("Failed", "danger"),
            "cancelled": ("Cancelled", "neutral"),
        }
        return mapping.get(normalized, ("Queued", "neutral"))

    def update_history_display(self):
        """Refresh the history panel cards."""
        self._clear_scroll_frame(self.history_scroll)

        history_count = len(self.download_history)
        completed_count = sum(1 for item in self.download_history if item.status == "completed")
        failed_count = sum(1 for item in self.download_history if item.status == "failed")
        self.history_tab_button.configure(text=f"History ({history_count})")
        self.history_summary_label.configure(
            text=f"{history_count} completed or failed download{'s' if history_count != 1 else ''}"
            if history_count
            else "Completed and failed jobs appear here during this session."
        )
        self.clear_history_button.configure(state="normal" if history_count else "disabled")
        self.clear_failed_button.configure(state="normal" if failed_count else "disabled")

        if history_count == 0:
            self._render_empty_state(
                self.history_scroll,
                "history",
                "No download history",
                "Completed and failed jobs will appear here after a batch finishes.",
            )
        else:
            for item in self.download_history:
                self._render_history_item(item)

    def _render_history_item(self, item: DownloadItem):
        card = ctk.CTkFrame(
            self.history_scroll,
            fg_color=self.colors.surface_alt,
            corner_radius=16,
            border_width=1,
            border_color=self.colors.border,
        )
        card.pack(fill="x", pady=(0, 10))

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)
        inner.grid_columnconfigure(1, weight=1)

        thumb = ctk.CTkLabel(
            inner,
            text="",
            image=self._thumbnail_image_for_item(item, HISTORY_THUMB_SIZE, self.update_history_display),
        )
        thumb.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14))

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(
            info,
            text=_ellipsize(item.title or "Untitled", 94),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.colors.text_primary,
            anchor="w",
            justify="left",
            wraplength=560,
        ).pack(anchor="w")

        meta = ctk.CTkFrame(info, fg_color="transparent")
        meta.pack(anchor="w", pady=(6, 0))

        self._tag(meta, "MP4" if item.item_type == "video" else "MP3", icon="video" if item.item_type == "video" else "music")
        self._tag(meta, _format_timestamp(item.finished_at))

        side = ctk.CTkFrame(inner, fg_color="transparent")
        side.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(14, 0))

        icon_name = "check_circle" if item.status == "completed" else "alert_circle"
        icon_color = self.colors.success if item.status == "completed" else self.colors.danger

        ctk.CTkLabel(
            side,
            text="",
            image=self.visuals.icon(icon_name, 18, icon_color),
        ).pack(anchor="e")

        link_btn = ctk.CTkButton(
            side,
            text="",
            image=self.visuals.icon("external", 14, self.colors.text_secondary),
            width=30,
            height=30,
            corner_radius=12,
            fg_color=self.colors.surface_soft,
            hover_color=self.colors.secondary_hover,
            border_width=1,
            border_color=self.colors.border,
            command=lambda url=item.source_url or item.url: self._open_external(url),
            state="normal" if (item.source_url or item.url) else "disabled",
        )
        link_btn.pack(anchor="e", pady=(8, 0))

    def remove_from_queue(self, index: int):
        """Remove an item from the queue."""
        if self._download_active:
            item = self.download_queue[index] if 0 <= index < len(self.download_queue) else None
            if item and item.status == "downloading":
                return

        if 0 <= index < len(self.download_queue):
            item = self.download_queue.pop(index)
            if getattr(item, "cached_thumbnail_path", None) and not any(
                other.cached_thumbnail_path == item.cached_thumbnail_path
                for other in (self.download_queue + self.download_history)
            ):
                self.thumbnail_cache.remove_path(item.cached_thumbnail_path)
            self.update_queue_display()

    def clear_history(self):
        if not self.download_history:
            return
        if not messagebox.askyesno("Clear History", "Remove all history items from this session?"):
            return
        self.thumbnail_cache.remove_for_items(self.download_history)
        self.download_history.clear()
        self._save_history()
        self.update_history_display()

    def clear_failed_history(self):
        """Clear only failed downloads from history."""
        failed_items = [item for item in self.download_history if item.status == "failed"]
        if not failed_items:
            return
        if not messagebox.askyesno("Clear Failed", f"Remove {len(failed_items)} failed download{'s' if len(failed_items) != 1 else ''} from history?"):
            return
        self.thumbnail_cache.remove_for_items(failed_items)
        self.download_history = [item for item in self.download_history if item.status != "failed"]
        self._save_history()
        self.update_history_display()

    def _open_external(self, url: Optional[str]):
        if not url:
            return
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def start_download(self):
        """Start downloading all queued items."""
        if self._download_active:
            messagebox.showinfo("Download Running", "A download is already in progress.")
            return

        if len(self.download_queue) == 0:
            messagebox.showinfo("Queue Empty", "Add at least one item to the queue first.")
            return

        folder = filedialog.askdirectory(title="Select Download Folder")
        if not folder:
            return

        thread = threading.Thread(target=self.download_all, args=(folder,))
        thread.daemon = True
        thread.start()

    def _snapshot_files(self, folder: str) -> set:
        """Capture all current files under the target folder for cancellation cleanup."""
        paths = set()
        if not folder or not os.path.isdir(folder):
            return paths
        for root, _, files in os.walk(folder):
            for name in files:
                paths.add(os.path.abspath(os.path.join(root, name)))
        return paths

    def _delete_session_files(self):
        """Delete files produced during the current session when the user cancels."""
        for file_path in sorted(self._session_created_files, reverse=True):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception:
                pass

        self._session_created_files.clear()

    def _request_cancel_download(self):
        """Ask the current worker to stop and keep the queue available for retry."""
        if not self._download_active:
            return
        self._cancel_requested = True
        if self.progress_dialog:
            self.after(0, lambda: self.progress_dialog.status_message.configure(text="Cancelling download and cleaning files..."))
            self.after(0, lambda: self.progress_dialog.set_cancel_enabled(False))

    def _is_cancel_requested(self) -> bool:
        return bool(self._cancel_requested)

    def _total_size_text(self) -> str:
        """Return a user-friendly total size label for progress text."""
        if getattr(self, "total_estimated_bytes", None):
            return format_bytes(self.total_estimated_bytes)
        if getattr(self, "_estimating_size", False):
            return "Estimating..."
        return "Unknown"

    def _update_queue_status_label(self, current: int, total: int):
        """Display clear queue progress with total size."""
        text = f"Download {current}/{total}  |  Total size: {self._total_size_text()}"
        if self.progress_dialog:
            self.after(0, lambda t=text: self.progress_dialog.queue_status_label.configure(text=t))

    def _download_unit_count(self, item: DownloadItem) -> int:
        """Count how many concrete downloads a queue item represents."""
        if item.is_playlist and item.merge_playlist:
            playlist_items = [part for part in (item.playlist_items or "").split(",") if part.strip()]
            if playlist_items:
                return len(playlist_items)
        return 1

    def _current_overall_download_position(self) -> int:
        total = max(1, getattr(self, "current_total_items", 1))
        processed = getattr(self, "_processed_download_units", 0)
        current_completed = getattr(self, "_current_item_completed_units", 0)
        return min(total, processed + current_completed + 1)

    def _overall_unit_percent(self, current_percent: float) -> float:
        total = max(1, getattr(self, "current_total_items", 1))
        processed = getattr(self, "_processed_download_units", 0)
        current_completed = getattr(self, "_current_item_completed_units", 0)
        active_fraction = max(0.0, min(1.0, float(current_percent) / 100.0))
        progress_units = processed + current_completed + active_fraction
        return min(100.0, (progress_units / total) * 100.0)

    def _format_progress_status(self, status_text: str) -> str:
        total = max(1, getattr(self, "current_total_items", 1))
        current = self._current_overall_download_position()
        current_item_total = max(1, getattr(self, "_current_item_total_units", 1))

        if current_item_total > 1:
            playlist_index = max(1, min(getattr(self, "_current_playlist_index", 1), current_item_total))
            return f"{status_text} (Video {playlist_index}/{current_item_total}  |  Download {current}/{total})"
        return f"{status_text} (Download {current}/{total})"

    def _update_progress_item_meta(self, item: DownloadItem):
        if not self.progress_dialog:
            return

        channel = getattr(item, "channel", None) or "YouTube"
        if item.is_playlist and item.merge_playlist and getattr(self, "_current_item_total_units", 1) > 1:
            playlist_index = max(1, min(getattr(self, "_current_playlist_index", 1), getattr(self, "_current_item_total_units", 1)))
            mode = "Playlist video" if item.item_type == "video" else "Playlist audio"
            text = f"{mode}  |  {channel}  |  Video {playlist_index}/{self._current_item_total_units}"
        else:
            mode = "Video download" if item.item_type == "video" else "Audio download"
            text = f"{mode}  |  {channel}"

        self.after(0, lambda value=text: self.progress_dialog.item_meta_label.configure(text=value))

    def _pick_primary_output(self, file_paths: Iterable[str]) -> Optional[str]:
        candidates = [path for path in file_paths if path and os.path.isfile(path)]
        if not candidates:
            return None

        try:
            return max(candidates, key=lambda path: (os.path.getsize(path), path.lower()))
        except Exception:
            return sorted(candidates)[0]

    def _save_history(self):
        save_history_items(self.download_history)

    def _load_history(self):
        self.download_history = load_history_items()

    def _record_history(self, item: DownloadItem, status: str, output_candidates: Optional[Iterable[str]] = None, error_message: Optional[str] = None):
        entry = copy.deepcopy(item)
        entry.status = status
        entry.finished_at = datetime.now()
        entry.output_path = self._pick_primary_output(output_candidates or [])
        entry.error_message = error_message
        self.download_history.insert(0, entry)
        self._save_history()
        self.after(0, self.update_history_display)

    def download_all(self, folder: str):
        """Download all queued items with progress tracking."""
        self._download_active = True
        self._cancel_requested = False
        self._session_created_files = set()
        self._download_folder = folder

        for item in self.download_queue:
            item.status = "queued"

        self.after(0, self.update_queue_display)

        self.progress_dialog = None
        self._dialog_ready = threading.Event()
        self.after(0, self._show_progress_dialog)
        self._dialog_ready.wait(timeout=5)

        if self.progress_dialog is None:
            self._download_active = False
            self._cancel_requested = False
            self.after(0, lambda: messagebox.showerror("Error", "Could not create the progress dialog."))
            return

        downloader = Downloader(cookie_manager=self.cookie_manager)
        total_items = sum(self._download_unit_count(item) for item in self.download_queue)
        self.current_total_items = max(1, total_items)
        self._estimating_size = True
        self._processed_download_units = 0
        self._current_item_total_units = 1
        self._current_item_completed_units = 0
        self._current_playlist_index = 1

        self.after(0, lambda: self.progress_dialog.update_totals(self.current_total_items, 0))
        self.after(0, lambda: self.progress_dialog.status_message.configure(text="Estimating download size..."))
        self._update_queue_status_label(0, self.current_total_items)
        self.after(0, lambda: self.progress_dialog.total_size_label.configure(text="Estimating..."))

        total_estimated_size = 0
        for item in self.download_queue:
            if self._cancel_requested:
                break
            try:
                size = downloader.estimate_size(item.url, item.item_type, item.quality, item.audio_format)
                if size:
                    item.estimated_size = size
                    total_estimated_size += size
            except Exception:
                pass

        self.total_estimated_bytes = total_estimated_size if total_estimated_size > 0 else None
        self._estimating_size = False
        self.completed_bytes = 0
        self.current_item_bytes = 0
        self.speed_smoother = SpeedSmoother()

        if self.total_estimated_bytes:
            self.after(0, lambda sz=format_bytes(self.total_estimated_bytes): self.progress_dialog.total_size_label.configure(text=sz))
        else:
            self.after(0, lambda: self.progress_dialog.total_size_label.configure(text="Unknown"))

        self._update_queue_status_label(0, self.current_total_items)

        cancelled = False
        had_errors = False

        for idx, item in enumerate(self.download_queue):
            if self._cancel_requested:
                cancelled = True
                break

            try:
                self.current_item_index = idx
                self.current_item_bytes = 0
                self._current_item_total_units = self._download_unit_count(item)
                self._current_item_completed_units = 0
                self._current_playlist_index = 1
                before_item_files = self._snapshot_files(folder)
                item.status = "downloading"

                current_download_num = self._current_overall_download_position()
                self.after(0, self.update_queue_display)
                self.after(
                    0,
                    lambda current_item=item: self.progress_dialog.update_current_item(
                        current_item,
                        self._thumbnail_image_for_item(current_item, PROGRESS_THUMB_SIZE, self._refresh_progress_current_thumbnail),
                    ),
                )
                self._update_progress_item_meta(item)
                self.after(0, lambda processed=self._processed_download_units, total=self.current_total_items: self.progress_dialog.update_totals(total, processed))
                self._update_queue_status_label(current_download_num, self.current_total_items)
                self.after(0, lambda title=item.title: self.progress_dialog.progress_label.configure(text=_ellipsize(title, 64)))
                self.after(0, lambda text=self._format_progress_status("Downloading selected quality..."): self.progress_dialog.status_message.configure(text=text))

                def progress_hook(progress_data):
                    self._handle_progress(progress_data, item)

                downloader.download_item(item, folder, progress_hook, should_cancel=self._is_cancel_requested)

                after_item_files = self._snapshot_files(folder)
                created_files = after_item_files - before_item_files
                self._session_created_files.update(created_files)

                if item.estimated_size:
                    self.completed_bytes += item.estimated_size
                else:
                    self.completed_bytes += self.current_item_bytes

                item.status = "completed"
                item.output_path = self._pick_primary_output(created_files)
                self._processed_download_units += self._current_item_total_units
                self._record_history(item, "completed", created_files)
                self.after(0, self.update_queue_display)
                self.after(0, lambda processed=self._processed_download_units, total=self.current_total_items: self.progress_dialog.update_totals(total, processed))

            except Exception as exc:
                if isinstance(exc, DownloadCancelledError):
                    item.status = "cancelled"
                    cancelled = True
                    self.after(0, self.update_queue_display)
                    break

                had_errors = True
                item.status = "failed"
                item.error_message = str(exc)
                self._processed_download_units += self._current_item_total_units
                self._record_history(item, "failed", error_message=str(exc))
                self.after(0, self.update_queue_display)
                self.after(0, lambda processed=self._processed_download_units, total=self.current_total_items: self.progress_dialog.update_totals(total, processed))

                if isinstance(exc, MissingFFmpegError):
                    error_title = "FFmpeg Required"
                elif isinstance(exc, NoCompatibleFormatError):
                    error_title = "No Compatible Format"
                elif isinstance(exc, MergeFailureError):
                    error_title = "Merge Failed"
                elif isinstance(exc, DirectDownloadError):
                    error_title = "Direct Download Failed"
                else:
                    error_title = "Download Error"

                self.after(0, lambda err=str(exc), i=idx, title=error_title: messagebox.showerror(title, f"Error downloading item {i + 1}:\n{err}"))

        if cancelled:
            self._delete_session_files()

        self.after(0, lambda c=cancelled, e=had_errors: self._download_complete(cancelled=c, had_errors=e))

    def _handle_progress(self, progress_data: dict, item: DownloadItem):
        """Handle progress updates from yt-dlp."""
        if progress_data.get("status") == "playlist_item":
            playlist_total = max(1, int(progress_data.get("playlist_total") or getattr(self, "_current_item_total_units", 1)))
            playlist_index = max(1, min(int(progress_data.get("playlist_index") or 1), playlist_total))

            self._current_item_total_units = playlist_total
            self._current_playlist_index = playlist_index
            self._current_item_completed_units = max(0, playlist_index - 1)

            current = self._current_overall_download_position()
            total = max(1, getattr(self, "current_total_items", 1))
            done = min(total, getattr(self, "_processed_download_units", 0) + self._current_item_completed_units)

            if self.progress_dialog:
                self.after(0, lambda processed=done, total_items=total: self.progress_dialog.update_totals(total_items, processed))
                self.after(0, lambda text=self._format_progress_status("Downloading playlist video..."): self.progress_dialog.status_message.configure(text=text))

            self._update_progress_item_meta(item)
            self._update_queue_status_label(current, total)
            return

        if progress_data.get("status") == "stage":
            stage = progress_data.get("stage", "")
            stage_map = {
                "fetching formats": "Fetching formats...",
                "formats loaded": "Formats loaded",
                "downloading selected quality": "Downloading selected quality...",
                "downloading video stream": "Downloading video stream...",
                "downloading audio stream": "Downloading audio stream...",
                "merging streams": "Merging streams...",
                "completed": "Completed",
            }
            status_text = stage_map.get(stage, stage)
            current = self._current_overall_download_position()
            total = max(1, getattr(self, "current_total_items", 1))
            if self.progress_dialog:
                self.after(0, lambda t=self._format_progress_status(status_text): self.progress_dialog.status_message.configure(text=t))
            self._update_queue_status_label(current, total)
            return

        if progress_data.get("status") == "downloading":
            try:
                if progress_data.get("percent") is not None:
                    percent = max(0.0, min(100.0, float(progress_data.get("percent", 0))))
                    overall_percent = self._overall_unit_percent(percent)
                    if self.progress_dialog:
                        self.after(0, lambda p=overall_percent: self.progress_dialog.percent_label.configure(text=f"{p:.1f}%"))
                        self.after(0, lambda p=overall_percent / 100: self.progress_dialog.progress_bar.set(p))

                        speed_text = progress_data.get("speed_text") or "--"
                        eta_text = progress_data.get("eta_text") or "--"
                        self.after(0, lambda s=speed_text: self.progress_dialog.speed_label.configure(text=s))
                        self.after(0, lambda e=eta_text: self.progress_dialog.eta_label.configure(text=e))
                    return

                downloaded = progress_data.get("downloaded_bytes") or 0
                total = progress_data.get("total_bytes") or progress_data.get("total_bytes_estimate") or 0
                speed = progress_data.get("speed") or 0

                downloaded = float(downloaded) if downloaded else 0
                total = float(total) if total else 0
                speed = float(speed) if speed else 0

                if downloaded > self.current_item_bytes:
                    self.current_item_bytes = downloaded

                if self.total_estimated_bytes and self.total_estimated_bytes > 0:
                    overall_bytes = self.completed_bytes + self.current_item_bytes
                    byte_percent = min(100.0, (overall_bytes / self.total_estimated_bytes) * 100.0)
                    overall_percent = max(byte_percent, self._overall_unit_percent((downloaded / total) * 100 if total else 0))

                    if speed:
                        smoothed_speed = self.speed_smoother.update(speed)
                        remaining_bytes = self.total_estimated_bytes - overall_bytes
                        eta_seconds = remaining_bytes / smoothed_speed if smoothed_speed > 0 else 0
                    else:
                        smoothed_speed = 0
                        eta_seconds = 0

                    if self.progress_dialog:
                        self.after(0, lambda p=overall_percent: self.progress_dialog.percent_label.configure(text=f"{p:.1f}%"))
                        self.after(0, lambda p=overall_percent / 100: self.progress_dialog.progress_bar.set(p))
                        self.after(0, lambda s=format_speed(smoothed_speed if smoothed_speed else speed): self.progress_dialog.speed_label.configure(text=s))
                        self.after(0, lambda e=format_eta(eta_seconds): self.progress_dialog.eta_label.configure(text=e))
                        self.after(0, lambda sz=format_bytes(overall_bytes): self.progress_dialog.size_label.configure(text=sz))
                else:
                    if total and self.progress_dialog:
                        percent = (downloaded / total) * 100
                        overall_percent = self._overall_unit_percent(percent)
                        self.after(0, lambda p=overall_percent: self.progress_dialog.percent_label.configure(text=f"{p:.1f}%"))
                        self.after(0, lambda p=overall_percent / 100: self.progress_dialog.progress_bar.set(p))

                    if self.progress_dialog:
                        self.after(0, lambda s=format_speed(speed): self.progress_dialog.speed_label.configure(text=s))
                        self.after(0, lambda e=format_eta(progress_data.get("eta", 0)): self.progress_dialog.eta_label.configure(text=e))
                        self.after(0, lambda sz=format_bytes(downloaded): self.progress_dialog.size_label.configure(text=sz))

            except Exception as exc:
                print(f"Progress hook error: {exc}")

        elif progress_data.get("status") == "finished":
            current = self._current_overall_download_position()
            total = max(1, getattr(self, "current_total_items", 1))
            if self.progress_dialog:
                self.after(0, lambda text=self._format_progress_status("Processing file..."): self.progress_dialog.status_message.configure(text=text))
            self._update_queue_status_label(current, total)

    def _show_progress_dialog(self):
        """Show the progress dialog."""
        self.progress_dialog = ProgressDialog(self, self.colors, on_cancel=self._request_cancel_download)
        self.progress_dialog.update()
        if hasattr(self, "_dialog_ready"):
            self._dialog_ready.set()

    def _download_complete(self, cancelled: bool = False, had_errors: bool = False):
        """Handle the end of a batch download."""
        if self.progress_dialog:
            self.progress_dialog.destroy()
            self.progress_dialog = None

        self._download_active = False
        self._cancel_requested = False
        self._download_folder = None

        if cancelled:
            for item in self.download_queue:
                if item.status != "failed":
                    item.status = "queued"
            self.update_queue_display()
            self.update_history_display()
            messagebox.showinfo("Cancelled", "Download cancelled. The queue was kept so you can retry.")
            return

        if had_errors:
            self.download_queue.clear()
            self.update_queue_display()
            self.update_history_display()
            messagebox.showwarning("Completed with Errors", "Download finished, but some items failed.")
            return

        self.download_queue.clear()
        self.update_queue_display()
        self.update_history_display()
        messagebox.showinfo("Complete", "All downloads completed successfully.")
