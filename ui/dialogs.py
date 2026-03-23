"""Dialog windows: installer, options, and progress."""
from __future__ import annotations

import threading
import webbrowser
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import customtkinter as ctk
from tkinter import messagebox

from core.models import DownloadItem
from ui.visual_assets import VisualAssets
from utils.format import format_bytes
from utils.media import resolve_thumbnail_url


PREVIEW_THUMB_SIZE = (144, 81)
PROGRESS_THUMB_SIZE = (96, 54)


def _ellipsize(value: Optional[str], limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


class InstallerDialog(ctk.CTkToplevel):
    """Modal dialog for installing yt-dlp."""

    def __init__(self, parent, theme_colors, on_success: Callable, on_failure: Callable):
        super().__init__(parent)

        self.parent = parent
        self.theme_colors = theme_colors
        self.visuals = VisualAssets(theme_colors)
        self.on_success = on_success
        self.on_failure = on_failure
        self.installing = False

        self.title("Installing Dependencies")
        self.geometry("620x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self._center_on_parent()
        parent.bind("<Configure>", self._on_parent_move)

        self._create_ui()
        self._start_installation()

    def _center_on_parent(self):
        self.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_w = self.parent.winfo_width()
        parent_h = self.parent.winfo_height()
        x = parent_x + (parent_w - 620) // 2
        y = parent_y + (parent_h - 420) // 2
        self.geometry(f"+{x}+{y}")

    def _on_parent_move(self, _event=None):
        if self.winfo_exists():
            self.after(10, self._center_on_parent)

    def _create_ui(self):
        root = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        root.pack(fill="both", expand=True)

        header = ctk.CTkFrame(root, fg_color=self.theme_colors.surface, corner_radius=0)
        header.pack(fill="x")

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=24, pady=20)

        ctk.CTkLabel(
            header_inner,
            text="",
            image=self.visuals.brand_mark(34),
        ).pack(side="left", padx=(0, 12))

        text_col = ctk.CTkFrame(header_inner, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            text_col,
            text="Installing yt-dlp",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            text_col,
            text="The app can finish setup automatically for this environment.",
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_muted,
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        body = ctk.CTkFrame(root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=22)

        log_shell = ctk.CTkFrame(
            body,
            fg_color=self.theme_colors.surface_alt,
            corner_radius=18,
            border_width=1,
            border_color=self.theme_colors.border,
        )
        log_shell.pack(fill="both", expand=True)

        self.log_text = ctk.CTkTextbox(
            log_shell,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color=self.theme_colors.surface_alt,
            text_color=self.theme_colors.text_primary,
            wrap="word",
            state="disabled",
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=12)

        self.status_label = ctk.CTkLabel(
            body,
            text="Starting...",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_muted,
        )
        self.status_label.pack(anchor="w", pady=(12, 0))

    def _log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_installation(self):
        self.installing = True
        thread = threading.Thread(target=self._install_thread)
        thread.daemon = True
        thread.start()

    def _install_thread(self):
        from core.deps import install_yt_dlp

        def progress_callback(msg):
            self.after(0, lambda m=msg: self._log(m))
            self.after(0, lambda m=msg: self.status_label.configure(text=m[:90]))

        success, message = install_yt_dlp(progress_callback)
        self.installing = False
        self.after(0, lambda: self._installation_complete(success, message))

    def _installation_complete(self, success: bool, message: str):
        if success:
            self._log("\nInstallation successful.")
            self.status_label.configure(text="Installation complete.", text_color=self.theme_colors.success)
            self.after(800, self._close_success)
            return

        self._log("\nInstallation failed.")
        self._log(message)
        self.status_label.configure(text="Installation failed. Review the log for details.", text_color=self.theme_colors.danger)
        self._show_failure_buttons()

    def _show_failure_buttons(self):
        footer = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        footer.pack(fill="x", padx=22, pady=(0, 20))

        ctk.CTkButton(
            footer,
            text="Retry",
            width=120,
            height=38,
            corner_radius=14,
            fg_color=self.theme_colors.primary,
            hover_color=self.theme_colors.primary_hover,
            command=self._retry,
        ).pack(side="left")

        ctk.CTkButton(
            footer,
            text="Exit",
            width=120,
            height=38,
            corner_radius=14,
            fg_color=self.theme_colors.surface_alt,
            hover_color=self.theme_colors.secondary_hover,
            text_color=self.theme_colors.danger,
            border_width=1,
            border_color=self.theme_colors.border,
            command=self._close_failure,
        ).pack(side="right")

    def _retry(self):
        for widget in self.winfo_children():
            if widget is not self.winfo_children()[0]:
                widget.destroy()
        self._create_ui()
        self._start_installation()

    def _close_success(self):
        self.destroy()
        self.on_success()

    def _close_failure(self):
        self.destroy()
        self.on_failure()

    def _on_close_attempt(self):
        if not self.installing:
            self._close_failure()


class OptionsDialog(ctk.CTkToplevel):
    """Dialog for configuring download options."""

    def __init__(self, parent, theme_colors, url, info, callback, cookie_manager=None, thumbnail_cache=None):
        super().__init__(parent)

        self.theme_colors = theme_colors
        self.visuals = VisualAssets(theme_colors)
        self.url = url
        self.info = info
        self.callback = callback
        self.cookie_manager = cookie_manager
        self.thumbnail_cache = thumbnail_cache
        self.preview_thumb_image = None

        self.download_type = ctk.StringVar(value="video")
        self.merge_playlist_var = ctk.StringVar(value="separate")
        self.quality_var = ctk.StringVar(value="")
        self.audio_quality_var = ctk.StringVar(value="256")

        self.available_formats = None
        self.format_lookup: Dict[str, Dict[str, Any]] = {}
        self.video_options: List[Dict[str, Any]] = []
        self.audio_options: List[Dict[str, Any]] = [
            {"value": "320", "label": "320 kbps", "meta": "Highest quality", "recommended": False},
            {"value": "256", "label": "256 kbps", "meta": "Recommended balance", "recommended": True},
            {"value": "192", "label": "192 kbps", "meta": "Smaller file size", "recommended": False},
            {"value": "128", "label": "128 kbps", "meta": "Compact", "recommended": False},
        ]

        self.title("Download Options")
        self.geometry("640x760")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._center()
        self._create_ui()

        if "entries" not in self.info:
            self._fetch_formats()
        else:
            self.video_options = [
                {"value": "2160", "label": "4K (2160p)", "meta": "Playlist auto selection", "recommended": False},
                {"value": "1440", "label": "2K (1440p)", "meta": "Playlist auto selection", "recommended": False},
                {"value": "1080", "label": "1080p", "meta": "Recommended", "recommended": True},
                {"value": "720", "label": "720p", "meta": "Good balance", "recommended": False},
                {"value": "480", "label": "480p", "meta": "Smaller file size", "recommended": False},
                {"value": "360", "label": "360p", "meta": "Low bandwidth", "recommended": False},
            ]
            self.quality_var.set("1080")
            self._refresh_dynamic_sections()

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 320
        y = (self.winfo_screenheight() // 2) - 380
        self.geometry(f"+{x}+{y}")

    def _create_ui(self):
        root = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        root.pack(fill="both", expand=True)

        scroll = ctk.CTkScrollableFrame(root, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=18, pady=(18, 10))

        self._build_preview(scroll)
        self._build_type_toggle(scroll)

        self.playlist_card = self._build_playlist_section(scroll)
        if "entries" not in self.info:
            self.playlist_card.pack_forget()

        self.video_card = self._build_option_card(scroll, "Video Quality")
        self.video_options_frame = ctk.CTkFrame(self.video_card, fg_color="transparent")
        self.video_options_frame.pack(fill="x")

        self.audio_card = self._build_option_card(scroll, "Audio Quality")
        self.audio_options_frame = ctk.CTkFrame(self.audio_card, fg_color="transparent")
        self.audio_options_frame.pack(fill="x")

        footer = ctk.CTkFrame(root, fg_color=self.theme_colors.bg)
        footer.pack(fill="x", padx=18, pady=(6, 18))

        ctk.CTkButton(
            footer,
            text="Cancel",
            width=130,
            height=42,
            corner_radius=14,
            fg_color=self.theme_colors.surface_alt,
            hover_color=self.theme_colors.secondary_hover,
            text_color=self.theme_colors.text_primary,
            border_width=1,
            border_color=self.theme_colors.border,
            command=self._on_cancel,
        ).pack(side="left")

        self.add_button = ctk.CTkButton(
            footer,
            text="Add to Queue",
            width=180,
            height=42,
            corner_radius=14,
            fg_color=self.theme_colors.primary,
            hover_color=self.theme_colors.primary_hover,
            text_color=self.theme_colors.primary_fg,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_add,
        )
        self.add_button.pack(side="right")

        self._refresh_dynamic_sections()

    def _build_preview(self, parent):
        shell = ctk.CTkFrame(
            parent,
            fg_color=self.theme_colors.surface,
            corner_radius=22,
            border_width=1,
            border_color=self.theme_colors.border,
        )
        shell.pack(fill="x", pady=(0, 14))

        inner = ctk.CTkFrame(shell, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)
        inner.grid_columnconfigure(1, weight=1)

        item_type = "video"
        self.preview_thumb_image = self.visuals.media_tile(PREVIEW_THUMB_SIZE, item_type)
        self.preview_thumb = ctk.CTkLabel(
            inner,
            text="",
            image=self.preview_thumb_image,
        )
        self.preview_thumb.grid(row=0, column=0, sticky="nw", padx=(0, 14))

        info_col = ctk.CTkFrame(inner, fg_color="transparent")
        info_col.grid(row=0, column=1, sticky="nsew")

        title = self.info.get("title", "Unknown title")
        ctk.CTkLabel(
            info_col,
            text=_ellipsize(title, 72),
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w",
            wraplength=460,
            justify="left",
        ).pack(anchor="w")

        subtitle = self.info.get("uploader") or self.info.get("channel") or "YouTube"
        if "entries" in self.info:
            subtitle = f"{subtitle}  |  {len(self.info.get('entries', []))} videos in playlist"

        ctk.CTkLabel(
            info_col,
            text=subtitle,
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_muted,
            anchor="w",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self._load_preview_thumbnail_async()

    def _load_preview_thumbnail_async(self):
        thumbnail_url = (resolve_thumbnail_url(self.info) or "").strip()
        if not thumbnail_url or not self.thumbnail_cache:
            return

        cached_path = self.thumbnail_cache.get_cached_path(thumbnail_url)
        if cached_path:
            image = self.visuals.local_media_image(cached_path, PREVIEW_THUMB_SIZE, corner_radius=16)
            if image:
                self.preview_thumb_image = image
                self.preview_thumb.configure(image=image)
                return

        def worker():
            cached = self.thumbnail_cache.ensure_cached(thumbnail_url)

            def finish():
                if not (cached and self.winfo_exists()):
                    return
                image = self.visuals.local_media_image(cached, PREVIEW_THUMB_SIZE, corner_radius=16)
                if image:
                    self.preview_thumb_image = image
                    self.preview_thumb.configure(image=image)

            self.after(0, finish)

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()

    def _build_type_toggle(self, parent):
        card = self._build_option_card(parent, "Download Type")

        self.type_buttons = {}
        button_row = ctk.CTkFrame(card, fg_color="transparent")
        button_row.pack(fill="x")

        self.type_buttons["video"] = ctk.CTkButton(
            button_row,
            text="Video (MP4)",
            image=self.visuals.icon("video", 15, self.theme_colors.text_primary),
            compound="left",
            height=42,
            corner_radius=14,
            command=lambda: self._set_download_type("video"),
        )
        self.type_buttons["video"].pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.type_buttons["audio"] = ctk.CTkButton(
            button_row,
            text="Audio (MP3)",
            image=self.visuals.icon("music", 15, self.theme_colors.text_primary),
            compound="left",
            height=42,
            corner_radius=14,
            command=lambda: self._set_download_type("audio"),
        )
        self.type_buttons["audio"].pack(side="left", fill="x", expand=True, padx=(6, 0))

    def _build_playlist_section(self, parent):
        card = self._build_option_card(parent, "Playlist Options")

        mode_row = ctk.CTkFrame(card, fg_color="transparent")
        mode_row.pack(fill="x")

        self.playlist_mode_buttons = {}
        self.playlist_mode_buttons["separate"] = ctk.CTkButton(
            mode_row,
            text="Separate files",
            height=40,
            corner_radius=14,
            command=lambda: self._set_playlist_mode("separate"),
        )
        self.playlist_mode_buttons["separate"].pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.playlist_mode_buttons["merge"] = ctk.CTkButton(
            mode_row,
            text="Merge playlist",
            height=40,
            corner_radius=14,
            command=lambda: self._set_playlist_mode("merge"),
        )
        self.playlist_mode_buttons["merge"].pack(side="left", fill="x", expand=True, padx=(6, 0))

        ctk.CTkLabel(
            card,
            text="Custom file name for merged playlist",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.theme_colors.text_muted,
        ).pack(anchor="w", pady=(12, 4))

        self.custom_name_entry = ctk.CTkEntry(
            card,
            placeholder_text="Leave empty to use the playlist title",
            height=40,
            corner_radius=14,
        )
        self.custom_name_entry.pack(fill="x")

        return card.master

    def _build_option_card(self, parent, title: str):
        outer = ctk.CTkFrame(
            parent,
            fg_color=self.theme_colors.surface,
            corner_radius=22,
            border_width=1,
            border_color=self.theme_colors.border,
        )
        outer.pack(fill="x", pady=(0, 14))

        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)

        ctk.CTkLabel(
            inner,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme_colors.text_primary,
        ).pack(anchor="w", pady=(0, 10))

        return inner

    def _set_download_type(self, value: str):
        self.download_type.set(value)
        self._refresh_dynamic_sections()

    def _set_playlist_mode(self, value: str):
        self.merge_playlist_var.set(value)
        self._refresh_dynamic_sections()

    def _refresh_dynamic_sections(self):
        active_fg = self.theme_colors.primary
        inactive_fg = self.theme_colors.surface_alt

        for name, button in self.type_buttons.items():
            is_active = self.download_type.get() == name
            button.configure(
                fg_color=active_fg if is_active else inactive_fg,
                hover_color=self.theme_colors.primary_hover if is_active else self.theme_colors.secondary_hover,
                text_color=self.theme_colors.primary_fg if is_active else self.theme_colors.text_primary,
                border_width=1,
                border_color=self.theme_colors.border,
            )

        if "entries" in self.info:
            for name, button in self.playlist_mode_buttons.items():
                is_active = self.merge_playlist_var.get() == name
                button.configure(
                    fg_color=active_fg if is_active else inactive_fg,
                    hover_color=self.theme_colors.primary_hover if is_active else self.theme_colors.secondary_hover,
                    text_color=self.theme_colors.primary_fg if is_active else self.theme_colors.text_primary,
                    border_width=1,
                    border_color=self.theme_colors.border,
                )
            self.custom_name_entry.configure(state="normal" if self.merge_playlist_var.get() == "merge" else "disabled")

        if self.download_type.get() == "video":
            self.audio_card.master.pack_forget()
            self.video_card.master.pack(fill="x", pady=(0, 14))
        else:
            self.video_card.master.pack_forget()
            self.audio_card.master.pack(fill="x", pady=(0, 14))

        self._render_quality_rows()

    def _render_quality_rows(self):
        self._clear_frame(self.video_options_frame)
        self._clear_frame(self.audio_options_frame)

        if self.video_card.master.winfo_manager():
            if not self.video_options:
                ctk.CTkLabel(
                    self.video_options_frame,
                    text="Loading available qualities...",
                    font=ctk.CTkFont(size=12),
                    text_color=self.theme_colors.text_muted,
                ).pack(anchor="w")
            else:
                for option in self.video_options:
                    self._quality_row(
                        self.video_options_frame,
                        self.quality_var,
                        option["value"],
                        option["label"],
                        option.get("meta", ""),
                        option.get("recommended", False),
                        enabled=option.get("enabled", True),
                    )

        if self.audio_card.master.winfo_manager():
            for option in self.audio_options:
                self._quality_row(
                    self.audio_options_frame,
                    self.audio_quality_var,
                    option["value"],
                    option["label"],
                    option.get("meta", ""),
                    option.get("recommended", False),
                    enabled=True,
                )

    def _quality_row(self, parent, variable, value: str, label: str, meta: str, recommended: bool, enabled: bool = True):
        is_selected = variable.get() == value
        bg = self.theme_colors.pill_bg if is_selected else self.theme_colors.surface_alt
        border = self.theme_colors.primary if is_selected else self.theme_colors.border

        row = ctk.CTkFrame(parent, fg_color=bg, corner_radius=16, border_width=1, border_color=border)
        row.pack(fill="x", pady=(0, 8))

        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        inner.grid_columnconfigure(0, weight=1)

        radio = ctk.CTkRadioButton(
            inner,
            text=label,
            variable=variable,
            value=value,
            state="normal" if enabled else "disabled",
            command=self._refresh_dynamic_sections,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.theme_colors.text_primary,
        )
        radio.grid(row=0, column=0, sticky="w")

        if recommended:
            ctk.CTkLabel(
                inner,
                text="Recommended",
                fg_color=self.theme_colors.pill_bg,
                text_color=self.theme_colors.primary,
                corner_radius=999,
                font=ctk.CTkFont(size=10, weight="bold"),
                height=22,
            ).grid(row=0, column=1, sticky="e")

        if meta:
            ctk.CTkLabel(
                inner,
                text=meta,
                font=ctk.CTkFont(size=11),
                text_color=self.theme_colors.text_muted,
                anchor="w",
                justify="left",
                wraplength=520,
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=(28, 0), pady=(3, 0))

        def _select(_event=None):
            if enabled:
                variable.set(value)
                self._refresh_dynamic_sections()

        row.bind("<Button-1>", _select)
        inner.bind("<Button-1>", _select)

    def _clear_frame(self, frame):
        for child in frame.winfo_children():
            child.destroy()

    def _fetch_formats(self):
        from core.downloader import Downloader

        def fetch():
            try:
                downloader = Downloader(cookie_manager=self.cookie_manager)
                formats_data = downloader.get_available_video_formats(self.url)
                self.after(0, lambda: self._update_format_options(formats_data))
            except Exception as exc:
                self.after(0, lambda: self._update_format_options({"video_formats": [], "error": str(exc)}))

        thread = threading.Thread(target=fetch)
        thread.daemon = True
        thread.start()

    def _update_format_options(self, formats_data):
        self.available_formats = formats_data
        self.video_options = []
        self.format_lookup = {}

        video_formats = formats_data.get("video_formats", [])
        error = formats_data.get("error")

        if error and not video_formats:
            self.video_options.append({
                "value": "",
                "label": "No compatible video qualities were found",
                "meta": error,
                "recommended": False,
                "enabled": False,
            })
            self.quality_var.set("")
            self._refresh_dynamic_sections()
            return

        for fmt in video_formats:
            format_id = fmt["format_id"]
            filesize = fmt.get("filesize")
            meta = format_bytes(filesize) if filesize else "Video quality"
            if fmt.get("requires_merge"):
                meta += " - audio merge required"

            self.video_options.append({
                "value": format_id,
                "label": fmt["resolution"],
                "meta": meta,
                "recommended": str(fmt.get("height") or "") == "1080",
                "enabled": bool(fmt.get("audio_format_id")) if fmt.get("requires_merge") else True,
            })
            self.format_lookup[format_id] = fmt

        if self.video_options:
            default_value = next((option["value"] for option in self.video_options if option.get("recommended") and option.get("enabled", True)), None)
            if not default_value:
                default_value = next((option["value"] for option in self.video_options if option.get("enabled", True)), "")
            self.quality_var.set(default_value)

        self._refresh_dynamic_sections()

    def _resolve_playlist_entry_url(self, entry: dict) -> Optional[str]:
        if not entry:
            return None

        webpage_url = (entry.get("webpage_url") or "").strip()
        if webpage_url:
            return webpage_url

        raw_url = (entry.get("url") or "").strip()
        if raw_url:
            parsed = urlparse(raw_url)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                return raw_url

        video_id = (entry.get("id") or "").strip()
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

        return None

    def _select_playlist_videos(self) -> Optional[List[Dict[str, Any]]]:
        entries = self.info.get("entries", [])
        rows: List[Dict[str, Any]] = []

        for idx, entry in enumerate(entries, start=1):
            if not entry:
                continue
            video_url = self._resolve_playlist_entry_url(entry)
            if not video_url:
                continue

            playlist_index = entry.get("playlist_index") or idx
            rows.append({
                "playlist_index": int(playlist_index),
                "title": (entry.get("title") or "").strip() or f"Video {idx}",
                "url": video_url,
                "channel": entry.get("uploader") or entry.get("channel"),
                "duration_seconds": entry.get("duration"),
                "thumbnail_url": resolve_thumbnail_url(entry),
            })

        if not rows:
            messagebox.showerror("Playlist Error", "No downloadable videos were found in this playlist.")
            return []

        dialog = PlaylistSelectionDialog(self, self.theme_colors, rows)
        self.wait_window(dialog)
        if not dialog.confirmed:
            return None
        return dialog.get_selected_rows()

    def _on_add(self):
        if self.download_type.get() == "video" and not self.quality_var.get():
            messagebox.showerror("No Format", "No compatible quality option is available for this video.")
            return

        merge = self.merge_playlist_var.get() == "merge" if "entries" in self.info else False
        custom_name = self.custom_name_entry.get().strip() if hasattr(self, "custom_name_entry") else None
        is_playlist = "entries" in self.info

        selected_value = self.quality_var.get()
        format_id = None
        selected_audio_format_id = None
        requires_merge = False
        height = None
        quality_label = None

        if self.available_formats and self.download_type.get() == "video":
            selected_format = self.format_lookup.get(selected_value)
            if selected_format:
                format_id = selected_value
                quality_label = selected_format["resolution"]
                height = selected_format.get("height")
                requires_merge = bool(selected_format.get("requires_merge"))
                selected_audio_format_id = selected_format.get("audio_format_id")

                if requires_merge and not selected_audio_format_id:
                    messagebox.showerror("No Audio Stream", "The selected quality needs an audio stream, but no compatible stream was found.")
                    return

        if not format_id and self.download_type.get() == "video":
            if selected_value and selected_value.isdigit():
                height = int(selected_value)
                quality_label = f"{selected_value}p"
            else:
                quality_label = selected_value

        selected_playlist_rows: Optional[List[Dict[str, Any]]] = None
        playlist_items_value = None

        if is_playlist:
            selected_playlist_rows = self._select_playlist_videos()
            if selected_playlist_rows is None:
                return
            if not selected_playlist_rows:
                messagebox.showwarning("No Videos Selected", "Select at least one video from the playlist.")
                return
            playlist_items_value = ",".join(str(row["playlist_index"]) for row in selected_playlist_rows)

        if is_playlist and not merge and selected_playlist_rows is not None:
            items = []
            for row in selected_playlist_rows:
                item = DownloadItem(
                    url=row["url"],
                    item_type=self.download_type.get(),
                    quality=None,
                    audio_format=self.audio_quality_var.get(),
                    is_playlist=False,
                    merge_playlist=False,
                    custom_name=None,
                    title=row["title"],
                    quality_label=quality_label,
                    height=height or (int(selected_value) if selected_value.isdigit() else 1080),
                    requires_merge=requires_merge,
                    selected_audio_format_id=selected_audio_format_id,
                    selected_video_format_id=format_id,
                    channel=row.get("channel"),
                    thumbnail_url=row.get("thumbnail_url"),
                    cached_thumbnail_path=self.thumbnail_cache.get_cached_path(row.get("thumbnail_url")) if self.thumbnail_cache else None,
                    duration_seconds=row.get("duration_seconds"),
                    source_url=row["url"],
                )
                items.append(item)
            self.callback(items)
            self.destroy()
            return

        item = DownloadItem(
            url=self.url,
            item_type=self.download_type.get(),
            quality=format_id,
            audio_format=self.audio_quality_var.get(),
            is_playlist=is_playlist,
            merge_playlist=merge,
            custom_name=custom_name if custom_name else None,
            quality_label=quality_label,
            height=height,
            requires_merge=requires_merge,
            selected_audio_format_id=selected_audio_format_id,
            selected_video_format_id=format_id,
            playlist_items=playlist_items_value,
            title=(custom_name if custom_name else self.info.get("title", "Unknown")),
            channel=self.info.get("uploader") or self.info.get("channel"),
            thumbnail_url=(
                (selected_playlist_rows[0].get("thumbnail_url") if selected_playlist_rows else None)
                or resolve_thumbnail_url(self.info)
            ),
            cached_thumbnail_path=(
                self.thumbnail_cache.get_cached_path(
                    (selected_playlist_rows[0].get("thumbnail_url") if selected_playlist_rows else None)
                    or resolve_thumbnail_url(self.info)
                )
                if self.thumbnail_cache
                else None
            ),
            duration_seconds=self.info.get("duration"),
            source_url=self.url,
        )

        self.callback([item])
        self.destroy()

    def _on_cancel(self):
        self.callback([])
        self.destroy()


class PlaylistSelectionDialog(ctk.CTkToplevel):
    """Modal dialog for choosing playlist entries."""

    def __init__(self, parent, theme_colors, rows: List[Dict[str, Any]]):
        super().__init__(parent)

        self.theme_colors = theme_colors
        self.rows = rows
        self.confirmed = False
        self._vars: List[ctk.BooleanVar] = []

        self.title("Select Playlist Videos")
        self.geometry("700x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._center()
        self._create_ui()

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 350
        y = (self.winfo_screenheight() // 2) - 280
        self.geometry(f"+{x}+{y}")

    def _create_ui(self):
        root = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        root.pack(fill="both", expand=True)

        ctk.CTkLabel(
            root,
            text="Choose videos to keep",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.theme_colors.text_primary,
        ).pack(anchor="w", padx=20, pady=(20, 4))

        ctk.CTkLabel(
            root,
            text=f"{len(self.rows)} videos detected. All are selected by default.",
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_muted,
        ).pack(anchor="w", padx=20, pady=(0, 10))

        list_frame = ctk.CTkScrollableFrame(root, fg_color=self.theme_colors.surface)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        for row in self.rows:
            var = ctk.BooleanVar(value=True)
            self._vars.append(var)
            ctk.CTkCheckBox(
                list_frame,
                text=f"[{row['playlist_index']:>3}] {row['title']}",
                variable=var,
                onvalue=True,
                offvalue=False,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", pady=4, padx=6)

        footer = ctk.CTkFrame(root, fg_color=self.theme_colors.bg)
        footer.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            footer,
            text="Cancel",
            width=130,
            height=38,
            corner_radius=14,
            fg_color=self.theme_colors.surface_alt,
            hover_color=self.theme_colors.secondary_hover,
            border_width=1,
            border_color=self.theme_colors.border,
            command=self._on_cancel,
        ).pack(side="left")

        ctk.CTkButton(
            footer,
            text="Confirm",
            width=130,
            height=38,
            corner_radius=14,
            fg_color=self.theme_colors.primary,
            hover_color=self.theme_colors.primary_hover,
            command=self._on_confirm,
        ).pack(side="right")

    def _on_cancel(self):
        self.confirmed = False
        self.destroy()

    def _on_confirm(self):
        self.confirmed = True
        self.destroy()

    def get_selected_rows(self) -> List[Dict[str, Any]]:
        return [row for row, var in zip(self.rows, self._vars) if var.get()]


class ProgressDialog(ctk.CTkToplevel):
    """Dialog showing download progress."""

    def __init__(self, parent, theme_colors, on_cancel: Optional[Callable] = None):
        super().__init__(parent)

        self.theme_colors = theme_colors
        self.visuals = VisualAssets(theme_colors)
        self.on_cancel = on_cancel

        self.title("Downloading...")
        self.geometry("590x470")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._center()
        self._create_ui()

    def _center(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 295
        y = (self.winfo_screenheight() // 2) - 235
        self.geometry(f"+{x}+{y}")

    def _create_ui(self):
        root = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        root.pack(fill="both", expand=True)

        header = ctk.CTkFrame(root, fg_color=self.theme_colors.surface, corner_radius=0)
        header.pack(fill="x")

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=24, pady=20)

        ctk.CTkLabel(
            header_inner,
            text="",
            image=self.visuals.brand_mark(36),
        ).pack(side="left", padx=(0, 12))

        title_col = ctk.CTkFrame(header_inner, fg_color="transparent")
        title_col.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            title_col,
            text="Download in Progress",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w",
        ).pack(anchor="w")

        self.queue_status_label = ctk.CTkLabel(
            title_col,
            text="Preparing...",
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_muted,
            anchor="w",
        )
        self.queue_status_label.pack(anchor="w", pady=(3, 0))

        self.cancel_button = ctk.CTkButton(
            header_inner,
            text="Cancel Download",
            width=150,
            height=36,
            corner_radius=14,
            fg_color=self.theme_colors.surface_alt,
            hover_color=self.theme_colors.secondary_hover,
            text_color=self.theme_colors.danger,
            border_width=1,
            border_color=self.theme_colors.border,
            command=self._handle_cancel,
        )
        self.cancel_button.pack(side="right")

        body = ctk.CTkFrame(root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=22)

        current_card = ctk.CTkFrame(body, fg_color=self.theme_colors.surface, corner_radius=18, border_width=1, border_color=self.theme_colors.border)
        current_card.pack(fill="x", pady=(0, 14))

        current_inner = ctk.CTkFrame(current_card, fg_color="transparent")
        current_inner.pack(fill="x", padx=14, pady=14)
        current_inner.grid_columnconfigure(1, weight=1)

        self.current_thumb_image = self.visuals.media_tile(PROGRESS_THUMB_SIZE, "video")
        self.current_thumb = ctk.CTkLabel(current_inner, text="", image=self.current_thumb_image)
        self.current_thumb.grid(row=0, column=0, sticky="nw", padx=(0, 12))

        current_info = ctk.CTkFrame(current_inner, fg_color="transparent")
        current_info.grid(row=0, column=1, sticky="nsew")

        ctk.CTkLabel(
            current_info,
            text="Current Item",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self.theme_colors.primary,
        ).pack(anchor="w")

        self.progress_label = ctk.CTkLabel(
            current_info,
            text="Starting download...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w",
            wraplength=440,
            justify="left",
        )
        self.progress_label.pack(anchor="w", pady=(4, 0))

        self.item_meta_label = ctk.CTkLabel(
            current_info,
            text="Preparing media...",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_muted,
            anchor="w",
        )
        self.item_meta_label.pack(anchor="w", pady=(3, 0))

        progress_card = ctk.CTkFrame(body, fg_color=self.theme_colors.surface, corner_radius=20, border_width=1, border_color=self.theme_colors.border)
        progress_card.pack(fill="x", pady=(0, 14))

        progress_inner = ctk.CTkFrame(progress_card, fg_color="transparent")
        progress_inner.pack(fill="x", padx=16, pady=16)

        header_row = ctk.CTkFrame(progress_inner, fg_color="transparent")
        header_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            header_row,
            text="Overall Progress",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.theme_colors.text_primary,
        ).pack(side="left")

        self.percent_label = ctk.CTkLabel(
            header_row,
            text="0%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme_colors.text_primary,
        )
        self.percent_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            progress_inner,
            mode="determinate",
            height=16,
            corner_radius=8,
            fg_color=self.theme_colors.surface_alt,
            progress_color=self.theme_colors.primary,
        )
        self.progress_bar.pack(fill="x", pady=(0, 12))
        self.progress_bar.set(0)

        counts = ctk.CTkFrame(progress_inner, fg_color="transparent")
        counts.pack(fill="x", pady=(0, 12))

        self.total_count_label = self._stat_chip(counts, "Total", "0")
        self.done_count_label = self._stat_chip(counts, "Done", "0", text_color=self.theme_colors.success)
        self.remaining_count_label = self._stat_chip(counts, "Remaining", "0")

        stats = ctk.CTkFrame(progress_inner, fg_color="transparent")
        stats.pack(fill="x")

        self.speed_label = self._metric(stats, "Speed", 0)
        self.eta_label = self._metric(stats, "Time Left", 1)
        self.size_label = self._metric(stats, "Downloaded", 2)
        self.total_size_label = self._metric(stats, "Total Size", 3)

        self.status_message = ctk.CTkLabel(
            body,
            text="Please wait while your files are being downloaded...",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_muted,
        )
        self.status_message.pack(anchor="w")

    def _stat_chip(self, parent, label: str, value: str, text_color: Optional[str] = None):
        shell = ctk.CTkFrame(parent, fg_color=self.theme_colors.surface_alt, corner_radius=16)
        shell.pack(side="left", fill="x", expand=True, padx=4)
        ctk.CTkLabel(shell, text=label, font=ctk.CTkFont(size=10), text_color=self.theme_colors.text_muted).pack(pady=(8, 0))
        value_label = ctk.CTkLabel(shell, text=value, font=ctk.CTkFont(size=18, weight="bold"), text_color=text_color or self.theme_colors.text_primary)
        value_label.pack(pady=(2, 8))
        return value_label

    def _metric(self, parent, label: str, column: int):
        parent.grid_columnconfigure(column, weight=1, uniform="metrics")
        shell = ctk.CTkFrame(parent, fg_color="transparent")
        shell.grid(row=0, column=column, sticky="nsew", padx=4)
        ctk.CTkLabel(shell, text=label, font=ctk.CTkFont(size=10), text_color=self.theme_colors.text_muted).pack(anchor="w")
        value = ctk.CTkLabel(shell, text="--", font=ctk.CTkFont(size=13, weight="bold"), text_color=self.theme_colors.text_primary, anchor="w")
        value.pack(anchor="w", pady=(2, 0))
        return value

    def update_current_item(self, item, thumbnail_image=None):
        item_type = getattr(item, "item_type", "video")
        self.current_thumb_image = thumbnail_image or self.visuals.media_tile(PROGRESS_THUMB_SIZE, item_type)
        self.current_thumb.configure(image=self.current_thumb_image)
        channel = getattr(item, "channel", None) or "YouTube"
        mode = "Video download" if item_type == "video" else "Audio download"
        self.item_meta_label.configure(text=f"{mode}  |  {channel}")

    def update_totals(self, total: int, done: int):
        remaining = max(0, total - done)
        self.total_count_label.configure(text=str(total))
        self.done_count_label.configure(text=str(done))
        self.remaining_count_label.configure(text=str(remaining))

    def _handle_cancel(self):
        if callable(self.on_cancel):
            self.on_cancel()

    def set_cancel_enabled(self, enabled: bool):
        self.cancel_button.configure(state="normal" if enabled else "disabled")


class CookieInputDialog(ctk.CTkToplevel):
    """Modal dialog for inputting YouTube cookies."""

    def __init__(self, parent, theme_colors, on_save: Callable):
        super().__init__(parent)

        self.parent = parent
        self.theme_colors = theme_colors
        self.visuals = VisualAssets(theme_colors)
        self.on_save = on_save

        self.title("YouTube Authentication - Cookies")
        self.geometry("680x680")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._center_on_parent()
        parent.bind("<Configure>", self._on_parent_move)

        self._create_ui()

    def _center_on_parent(self):
        self.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_w = self.parent.winfo_width()
        parent_h = self.parent.winfo_height()
        x = parent_x + (parent_w - 680) // 2
        y = parent_y + (parent_h - 680) // 2
        self.geometry(f"+{x}+{y}")

    def _on_parent_move(self, _event=None):
        if self.winfo_exists():
            self.after(10, self._center_on_parent)

    def _create_ui(self):
        # Single unified container
        container = ctk.CTkFrame(
            self,
            fg_color=self.theme_colors.surface,
            corner_radius=0
        )
        container.pack(fill="both", expand=True)

        # Content area with padding
        content = ctk.CTkFrame(container, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=32, pady=32)

        # Title
        ctk.CTkLabel(
            content,
            text="Insert YouTube Cookies",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w",
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            content,
            text="Follow these steps to export your browser cookies:",
            font=ctk.CTkFont(size=13),
            text_color=self.theme_colors.text_secondary,
            anchor="w",
        ).pack(anchor="w", pady=(0, 24))

        # Instructions
        # Step 1 with clickable link
        step1_frame = ctk.CTkFrame(content, fg_color="transparent")
        step1_frame.pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            step1_frame,
            text="1. Go to ",
            font=ctk.CTkFont(size=13),
            text_color=self.theme_colors.text_primary,
            anchor="w",
        ).pack(side="left")

        link_button = ctk.CTkButton(
            step1_frame,
            text="Get cookies.txt LOCALLY",
            font=ctk.CTkFont(size=13, underline=True),
            text_color=self.theme_colors.primary,
            fg_color="transparent",
            hover_color=self.theme_colors.surface_alt,
            width=0,
            height=0,
            command=lambda: self._open_url("https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"),
        )
        link_button.pack(side="left")

        ctk.CTkLabel(
            step1_frame,
            text=" for your browser",
            font=ctk.CTkFont(size=13),
            text_color=self.theme_colors.text_primary,
            anchor="w",
        ).pack(side="left")

        # Steps 2-4
        steps = [
            "2. Open youtube.com",
            "3. Open the extension",
            "4. Copy and paste the cookies here:"
        ]

        for step in steps:
            ctk.CTkLabel(
                content,
                text=step,
                font=ctk.CTkFont(size=13),
                text_color=self.theme_colors.text_primary,
                anchor="w",
            ).pack(anchor="w", pady=(0, 8))

        # Text box label and action buttons row
        textbox_header = ctk.CTkFrame(content, fg_color="transparent")
        textbox_header.pack(fill="x", pady=(16, 8))

        ctk.CTkLabel(
            textbox_header,
            text="Paste cookies below:",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.theme_colors.text_muted,
            anchor="w",
        ).pack(side="left")

        # Action buttons for the textbox (Clear/Paste)
        textbox_actions = ctk.CTkFrame(textbox_header, fg_color="transparent")
        textbox_actions.pack(side="right")

        self.cookie_action_button = ctk.CTkButton(
            textbox_actions,
            text="Paste",
            image=self.visuals.icon("paste", 14, self.theme_colors.text_secondary),
            compound="left",
            width=76,
            height=28,
            corner_radius=10,
            fg_color=self.theme_colors.surface_alt,
            hover_color=self.theme_colors.secondary_hover,
            text_color=self.theme_colors.text_secondary,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._paste_cookies,
        )
        self.cookie_action_button.pack(side="left")

        self.cookie_textbox = ctk.CTkTextbox(
            content,
            font=ctk.CTkFont(size=10, family="Courier"),
            fg_color=self.theme_colors.input_bg,
            text_color=self.theme_colors.text_primary,
            border_width=2,
            border_color=self.theme_colors.border,
            wrap="none",
            height=200,
        )
        self.cookie_textbox.pack(fill="both", expand=True, pady=(0, 24))
        self.cookie_textbox.bind("<KeyRelease>", lambda _event: self._sync_cookie_action_button())

        # Buttons
        button_frame = ctk.CTkFrame(content, fg_color="transparent")
        button_frame.pack(fill="x")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.theme_colors.surface_alt,
            hover_color=self.theme_colors.secondary_hover,
            text_color=self.theme_colors.text_secondary,
            height=48,
            corner_radius=12,
            border_width=1,
            border_color=self.theme_colors.border,
            command=self._on_cancel,
        )
        cancel_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        save_button = ctk.CTkButton(
            button_frame,
            text="Save Cookies",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.theme_colors.primary,
            hover_color=self.theme_colors.primary_hover,
            text_color="#FFFFFF",
            height=48,
            corner_radius=12,
            command=self._on_save_click,
        )
        save_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def _open_url(self, url: str):
        webbrowser.open(url)

    def _paste_cookies(self):
        """Paste clipboard content into the cookie textbox."""
        try:
            clipboard_content = self.clipboard_get()
        except Exception:
            clipboard_content = ""

        if clipboard_content:
            self.cookie_textbox.delete("1.0", "end")
            self.cookie_textbox.insert("1.0", clipboard_content)
            self._sync_cookie_action_button()

    def _clear_cookies(self):
        """Clear the cookie textbox."""
        self.cookie_textbox.delete("1.0", "end")
        self._sync_cookie_action_button()

    def _sync_cookie_action_button(self):
        """Update the action button based on textbox content."""
        has_text = bool(self.cookie_textbox.get("1.0", "end-1c").strip())
        if has_text:
            self.cookie_action_button.configure(
                text="Clear",
                image=self.visuals.icon("close", 13, self.theme_colors.text_secondary),
                command=self._clear_cookies,
            )
        else:
            self.cookie_action_button.configure(
                text="Paste",
                image=self.visuals.icon("paste", 14, self.theme_colors.text_secondary),
                command=self._paste_cookies,
            )

    def _on_cancel(self):
        self.destroy()

    def _on_save_click(self):
        cookie_content = self.cookie_textbox.get("1.0", "end-1c").strip()
        if cookie_content:
            self.on_save(cookie_content)
            self.destroy()
        else:
            messagebox.showwarning("No Cookies", "Please paste your cookies before saving.")
