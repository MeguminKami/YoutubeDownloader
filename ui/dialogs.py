"""
Dialog windows: installer, options, progress
"""
import customtkinter as ctk
from tkinter import messagebox
import threading
import os
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
from PIL import Image
from core.models import DownloadItem
from utils.format import format_bytes, format_speed, format_eta


class InstallerDialog(ctk.CTkToplevel):
    """
    Modal dialog for installing yt-dlp dependency
    Stays attached to parent window
    """

    def __init__(self, parent, theme_colors, on_success: Callable, on_failure: Callable):
        super().__init__(parent)

        self.parent = parent
        self.theme_colors = theme_colors
        self.on_success = on_success
        self.on_failure = on_failure
        self.installing = False

        self.title("Installing Dependencies")
        self.geometry("600x400")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        self._center_on_parent()
        parent.bind('<Configure>', self._on_parent_move)

        self._create_ui()
        self._start_installation()


    def _center_on_parent(self):
        """Center dialog on parent window"""
        self.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_w = self.parent.winfo_width()
        parent_h = self.parent.winfo_height()

        x = parent_x + (parent_w - 600) // 2
        y = parent_y + (parent_h - 400) // 2
        self.geometry(f"+{x}+{y}")

    def _on_parent_move(self, event=None):
        """Reposition dialog when parent moves"""
        if self.winfo_exists():
            self.after(10, self._center_on_parent)

    def _create_ui(self):
        """Create installer UI"""
        main_frame = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        main_frame.pack(fill="both", expand=True)

        header = ctk.CTkLabel(
            main_frame,
            text="📦 Installing yt-dlp",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.theme_colors.accent_blue
        )
        header.pack(pady=(30, 10))

        subtitle = ctk.CTkLabel(
            main_frame,
            text="Please wait while we install required dependencies...",
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_secondary
        )
        subtitle.pack(pady=(0, 20))

        log_frame = ctk.CTkFrame(main_frame, fg_color=self.theme_colors.surface, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Courier", size=10),
            fg_color=self.theme_colors.surface,
            wrap="word",
            state="disabled"
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Starting...",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_tertiary
        )
        self.status_label.pack(pady=(0, 20))

    def _log(self, message: str):
        """Add message to log"""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_installation(self):
        """Start installation in background thread"""
        self.installing = True
        thread = threading.Thread(target=self._install_thread)
        thread.daemon = True
        thread.start()

    def _install_thread(self):
        """Installation thread"""
        from core.deps import install_yt_dlp

        def progress_callback(msg):
            self.after(0, lambda m=msg: self._log(m))
            self.after(0, lambda m=msg: self.status_label.configure(text=m[:80]))

        success, message = install_yt_dlp(progress_callback)

        self.installing = False
        self.after(0, lambda: self._installation_complete(success, message))

    def _installation_complete(self, success: bool, message: str):
        """Handle installation completion"""
        if success:
            self._log("\n✓ Installation successful!")
            self.status_label.configure(text="Installation complete!", text_color=self.theme_colors.accent_blue)
            self.after(1000, self._close_success)
        else:
            self._log(f"\n✗ Installation failed!")
            self._log(message)
            self.status_label.configure(text="Installation failed. See log for details.", text_color="#ef4444")
            self._show_failure_buttons()

    def _show_failure_buttons(self):
        """Show retry/exit buttons on failure"""
        btn_frame = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        retry_btn = ctk.CTkButton(
            btn_frame,
            text="Retry",
            command=self._retry,
            fg_color=self.theme_colors.accent_blue
        )
        retry_btn.pack(side="left", expand=True, padx=(0, 5))

        exit_btn = ctk.CTkButton(
            btn_frame,
            text="Exit",
            command=self._close_failure,
            fg_color="#ef4444"
        )
        exit_btn.pack(side="right", expand=True, padx=(5, 0))

    def _retry(self):
        """Retry installation"""
        for widget in self.winfo_children():
            if isinstance(widget, ctk.CTkFrame) and widget != self.winfo_children()[0]:
                widget.destroy()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._start_installation()

    def _close_success(self):
        """Close dialog on success"""
        self.destroy()
        self.on_success()

    def _close_failure(self):
        """Close dialog on failure"""
        self.destroy()
        self.on_failure()

    def _on_close_attempt(self):
        """Prevent closing during installation"""
        if not self.installing:
            self._close_failure()


class OptionsDialog(ctk.CTkToplevel):
    """Dialog for configuring download options"""

    def __init__(self, parent, theme_colors, url, info, callback):
        super().__init__(parent)

        self.theme_colors = theme_colors
        self.url = url
        self.info = info
        self.callback = callback
        self.available_formats = None
        self.format_lookup = {}
        self.video_format_widgets = []

        self.title("Download Options")
        self.geometry("600x750")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._center()
        self._create_ui()

        # Fetch available formats in background for non-playlist single videos
        if 'entries' not in self.info:
            self._fetch_formats()

    def _center(self):
        """Center dialog"""
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 300
        y = (self.winfo_screenheight() // 2) - 375
        self.geometry(f"+{x}+{y}")

    def _fetch_formats(self):
        """Fetch available formats in background"""
        import threading
        from core.downloader import Downloader

        def fetch():
            try:
                downloader = Downloader()
                # get_available_video_formats now returns a dict with 'video_formats' key
                formats_data = downloader.get_available_video_formats(self.url)
                self.after(0, lambda: self._update_format_options(formats_data))
            except Exception as e:
                print(f"Error fetching formats: {e}")
                self.after(0, lambda: self._update_format_options({'video_formats': [], 'error': str(e)}))

        thread = threading.Thread(target=fetch)
        thread.daemon = True
        thread.start()

    def _update_format_options(self, formats_data):
        """
        Update the video quality options with fetched formats.

        formats_data is a dict with 'video_formats' key containing list of format dicts:
        {
            'video_formats': [
                {'format_id': '137', 'height': 1080, 'fps': 30, 'ext': 'mp4',
                 'resolution': '1080p (MP4)', 'filesize': 12345678},
                ...
            ],
            'error': None or 'error message'
        }
        """
        self.available_formats = formats_data

        # Clear existing video format widgets
        for widget in self.video_format_widgets:
            widget.destroy()
        self.video_format_widgets.clear()

        # Remove loading label if exists
        if hasattr(self, 'loading_label') and self.loading_label:
            self.loading_label.destroy()
            self.loading_label = None

        # Extract video_formats list from the dict
        video_formats = formats_data.get('video_formats', [])
        error = formats_data.get('error')

        if error and not video_formats:
            # Show error message
            label = ctk.CTkLabel(
                self.video_quality_frame,
                text=f"Could not fetch qualities: {error}",
                font=ctk.CTkFont(size=11),
                text_color="#ef4444",
                wraplength=400
            )
            label.pack(anchor="w", pady=2)
            self.video_format_widgets.append(label)
            # Fall through to add fallback options

        if video_formats:
            self.format_lookup = {fmt['format_id']: fmt for fmt in video_formats}

            first_selectable = None
            for fmt in video_formats:
                format_id = fmt['format_id']
                resolution = fmt['resolution']
                requires_merge = fmt.get('requires_merge', False)
                has_compatible_audio = bool(fmt.get('audio_format_id')) if requires_merge else True

                if not has_compatible_audio:
                    resolution = f"{resolution} (no compatible audio stream)"

                if first_selectable is None and has_compatible_audio:
                    first_selectable = fmt

                rb = ctk.CTkRadioButton(
                    self.video_quality_frame,
                    text=resolution,  # Already formatted as "1080p 60fps (MP4) ~500MB"
                    variable=self.quality_var,
                    value=format_id,  # CRITICAL: Use format_id as value!
                    font=ctk.CTkFont(size=12),
                    state="normal" if has_compatible_audio else "disabled"
                )
                rb.pack(anchor="w", pady=2)
                self.video_format_widgets.append(rb)

                # Store resolution for display
                rb._resolution = resolution
                rb._format_id = format_id

            if first_selectable:
                self.quality_var.set(first_selectable['format_id'])
                self.selected_quality_display = first_selectable['resolution']
            else:
                self.quality_var.set("")
        else:
            # Fallback if no formats found
            label = ctk.CTkLabel(
                self.video_quality_frame,
                text="Using default quality options:",
                font=ctk.CTkFont(size=11),
                text_color=self.theme_colors.text_tertiary
            )
            label.pack(anchor="w", pady=2)
            self.video_format_widgets.append(label)

            # Add default fallback options (height-based selection)
            for resolution, height in [("1080p (Full HD)", "1080"), ("720p (HD)", "720"),
                                        ("480p (SD)", "480"), ("360p (Low)", "360")]:
                rb = ctk.CTkRadioButton(
                    self.video_quality_frame,
                    text=resolution,
                    variable=self.quality_var,
                    value=height,  # Use height for fallback
                    font=ctk.CTkFont(size=12)
                )
                rb.pack(anchor="w", pady=2)
                self.video_format_widgets.append(rb)

            # Set default
            self.quality_var.set("1080")

    def _create_ui(self):
        """Create options UI"""
        container = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        container.pack(fill="both", expand=True)

        scroll_frame = ctk.CTkScrollableFrame(container, fg_color=self.theme_colors.bg)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        is_playlist = 'entries' in self.info
        title_text = self.info.get('title', 'Unknown')

        title = ctk.CTkLabel(
            scroll_frame,
            text=title_text[:60] + "..." if len(title_text) > 60 else title_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            wraplength=550,
            text_color=self.theme_colors.text_primary
        )
        title.pack(pady=(0, 10))

        if is_playlist:
            count_label = ctk.CTkLabel(
                scroll_frame,
                text=f"Playlist with {len(self.info['entries'])} videos",
                font=ctk.CTkFont(size=13),
                text_color=self.theme_colors.accent_blue
            )
            count_label.pack(pady=(0, 20))

        # Download type
        type_frame = self._create_card(scroll_frame, "Download Type")
        self.download_type = ctk.StringVar(value="video")

        ctk.CTkRadioButton(
            type_frame,
            text="Video (MP4)",
            variable=self.download_type,
            value="video",
            font=ctk.CTkFont(size=13)
        ).pack(anchor="w", pady=2)

        ctk.CTkRadioButton(
            type_frame,
            text="Audio Only (MP3)",
            variable=self.download_type,
            value="audio",
            font=ctk.CTkFont(size=13)
        ).pack(anchor="w", pady=2)

        # Playlist options
        self.merge_playlist_var = None
        self.custom_name_entry = None

        if is_playlist:
            playlist_frame = self._create_card(scroll_frame, "Playlist Options")
            self.merge_playlist_var = ctk.StringVar(value="separate")

            ctk.CTkRadioButton(
                playlist_frame,
                text="Download each video separately",
                variable=self.merge_playlist_var,
                value="separate",
                font=ctk.CTkFont(size=13)
            ).pack(anchor="w", pady=2)

            ctk.CTkRadioButton(
                playlist_frame,
                text="Merge all into one file",
                variable=self.merge_playlist_var,
                value="merge",
                font=ctk.CTkFont(size=13)
            ).pack(anchor="w", pady=2)

            ctk.CTkLabel(
                playlist_frame,
                text="Custom name (for merged file):",
                font=ctk.CTkFont(size=12),
                text_color=self.theme_colors.text_tertiary
            ).pack(anchor="w", pady=(10, 5))

            self.custom_name_entry = ctk.CTkEntry(
                playlist_frame,
                placeholder_text="Leave empty to use playlist name",
                height=35,
                font=ctk.CTkFont(size=12)
            )
            self.custom_name_entry.pack(fill="x", pady=(0, 5))

        # Video quality
        self.video_quality_frame = self._create_card(scroll_frame, "Video Quality")
        self.quality_var = ctk.StringVar(value="1080")
        self.selected_quality_display = "1080p"

        # For playlists, show static options (can't fetch for each video)
        if is_playlist:
            for qual_name, qual_value in [("1080p (Full HD)", "1080"),
                                          ("720p (HD)", "720"), ("480p (SD)", "480"), ("360p (Low)", "360")]:
                rb = ctk.CTkRadioButton(
                    self.video_quality_frame,
                    text=qual_name,
                    variable=self.quality_var,
                    value=qual_value,
                    font=ctk.CTkFont(size=12)
                )
                rb.pack(anchor="w", pady=2)
                self.video_format_widgets.append(rb)
        else:
            # Show loading state while fetching formats
            self.loading_label = ctk.CTkLabel(
                self.video_quality_frame,
                text="Loading available qualities...",
                font=ctk.CTkFont(size=12),
                text_color=self.theme_colors.text_tertiary
            )
            self.loading_label.pack(anchor="w", pady=2)

        # Audio quality
        self.audio_quality_frame = self._create_card(scroll_frame, "Audio Quality")
        self.audio_quality_var = ctk.StringVar(value="192")

        for qual_name, qual_value in [("High (320 kbps)", "320"), ("Medium (192 kbps)", "192"),
                                      ("Low (128 kbps)", "128")]:
            ctk.CTkRadioButton(
                self.audio_quality_frame,
                text=qual_name,
                variable=self.audio_quality_var,
                value=qual_value,
                font=ctk.CTkFont(size=12)
            ).pack(anchor="w", pady=2)

        self.download_type.trace_add("write", self._on_type_change)
        self._on_type_change()

        # Buttons
        btn_frame = ctk.CTkFrame(container, fg_color=self.theme_colors.bg)
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=140,
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color=self.theme_colors.hover,
            command=self._on_cancel
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="Add to Queue",
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self.theme_colors.accent_blue,
            command=self._on_add
        ).pack(side="right")

    def _create_card(self, parent, title):
        """Create a card frame"""
        frame = ctk.CTkFrame(parent, fg_color=self.theme_colors.surface, corner_radius=10)
        frame.pack(fill="x", pady=(0, 15))

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(
            inner,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme_colors.text_primary
        ).pack(anchor="w", pady=(0, 10))

        return inner

    def _on_type_change(self, *args):
        """Toggle video/audio quality visibility"""
        if self.download_type.get() == "video":
            self.video_quality_frame.master.pack(fill="x", pady=(0, 15))
            self.audio_quality_frame.master.pack_forget()
        else:
            self.video_quality_frame.master.pack_forget()
            self.audio_quality_frame.master.pack(fill="x", pady=(0, 15))

    def _resolve_playlist_entry_url(self, entry: dict) -> Optional[str]:
        """Resolve a downloadable URL from playlist entry metadata."""
        if not entry:
            return None

        # Prefer canonical page URL when available.
        webpage_url = (entry.get('webpage_url') or '').strip()
        if webpage_url:
            return webpage_url

        raw_url = (entry.get('url') or '').strip()
        if raw_url:
            parsed = urlparse(raw_url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                return raw_url

        video_id = (entry.get('id') or '').strip()
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"

        return None

    def _on_add(self):
        """Add to queue"""
        if self.download_type.get() == "video" and not self.quality_var.get() and self.available_formats:
            messagebox.showerror("No Format", "No compatible quality option is available for this video.")
            return

        merge = self.merge_playlist_var.get() == "merge" if self.merge_playlist_var else False
        custom_name = self.custom_name_entry.get().strip() if self.custom_name_entry else None
        is_playlist = 'entries' in self.info

        # Get selected quality value
        selected_value = self.quality_var.get()

        # Determine if we have a format_id or a height value
        format_id = None
        selected_audio_format_id = None
        requires_merge = False
        height = None
        quality_label = None

        if self.available_formats and self.download_type.get() == "video":
            selected_format = self.format_lookup.get(selected_value)
            if selected_format:
                format_id = selected_value
                quality_label = selected_format['resolution']
                height = selected_format.get('height')
                requires_merge = bool(selected_format.get('requires_merge'))
                selected_audio_format_id = selected_format.get('audio_format_id')

                if requires_merge and not selected_audio_format_id:
                    messagebox.showerror("No Audio Stream", "The selected quality requires an audio stream, but no compatible audio format was found.")
                    return

        # If no format_id found, selected_value is a height (fallback/playlist mode)
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
            playlist_items_value = ",".join(str(row['playlist_index']) for row in selected_playlist_rows)

        # If it's a playlist and user wants separate files, add each selected video individually.
        if is_playlist and not merge and selected_playlist_rows is not None:
            items = []
            for row in selected_playlist_rows:
                item = DownloadItem(
                    url=row['url'],
                    item_type=self.download_type.get(),
                    quality=None,  # Playlist separate mode uses height-based selection
                    audio_format=self.audio_quality_var.get(),
                    is_playlist=False,
                    merge_playlist=False,
                    custom_name=None,
                    title=row['title'],
                    quality_label=quality_label,
                    height=height or (int(selected_value) if selected_value.isdigit() else 1080),
                    requires_merge=requires_merge,
                    selected_audio_format_id=selected_audio_format_id,
                    selected_video_format_id=format_id
                )
                items.append(item)
            self.callback(items)
        else:
            # Single video or merged playlist
            item = DownloadItem(
                url=self.url,
                item_type=self.download_type.get(),
                quality=format_id,  # format_id if available, None otherwise
                audio_format=self.audio_quality_var.get(),
                is_playlist=is_playlist,
                merge_playlist=merge,
                custom_name=custom_name if custom_name else None,
                quality_label=quality_label,
                height=height,
                requires_merge=requires_merge,
                selected_audio_format_id=selected_audio_format_id,
                selected_video_format_id=format_id,
                playlist_items=playlist_items_value
            )

            if is_playlist and merge:
                item.title = custom_name if custom_name else self.info.get('title', 'Playlist')
            else:
                item.title = self.info.get('title', 'Unknown')

            self.callback([item])  # Always return as list for consistency

        self.destroy()

    def _select_playlist_videos(self) -> Optional[List[Dict[str, Any]]]:
        """Open selection popup and return selected playlist rows or None on cancel."""
        entries = self.info.get('entries', [])
        rows: List[Dict[str, Any]] = []

        for idx, entry in enumerate(entries, start=1):
            if not entry:
                continue
            video_url = self._resolve_playlist_entry_url(entry)
            if not video_url:
                continue

            title = (entry.get('title') or '').strip() or f"Video {idx}"
            playlist_index = entry.get('playlist_index') or idx
            rows.append({
                'playlist_index': int(playlist_index),
                'title': title,
                'url': video_url,
            })

        if not rows:
            messagebox.showerror("Playlist Error", "No downloadable videos were found in this playlist.")
            return []

        dialog = PlaylistSelectionDialog(self, self.theme_colors, rows)
        self.wait_window(dialog)
        if not dialog.confirmed:
            return None
        return dialog.get_selected_rows()

    def _on_cancel(self):
        """Cancel"""
        self.callback([])
        self.destroy()


class PlaylistSelectionDialog(ctk.CTkToplevel):
    """Modal dialog to choose which playlist videos should be queued."""

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
            text=f"{len(self.rows)} videos detected (all selected by default)",
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_tertiary,
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
            ).pack(anchor="w", pady=3, padx=6)

        btns = ctk.CTkFrame(root, fg_color=self.theme_colors.bg)
        btns.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(
            btns,
            text="Cancel",
            width=130,
            height=38,
            fg_color=self.theme_colors.hover,
            command=self._on_cancel,
        ).pack(side="left")

        ctk.CTkButton(
            btns,
            text="Confirm",
            width=130,
            height=38,
            fg_color=self.theme_colors.accent_blue,
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
    """Dialog showing download progress"""

    def __init__(self, parent, theme_colors, on_cancel: Optional[Callable] = None):
        super().__init__(parent)

        self.theme_colors = theme_colors
        self.on_cancel = on_cancel
        self.logo_image = self._load_logo_image()

        self.title("Downloading...")
        self.geometry("550x400")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._center()
        self._create_ui()

    def _center(self):
        """Center dialog"""
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 275
        y = (self.winfo_screenheight() // 2) - 200
        self.geometry(f"+{x}+{y}")

    def _create_ui(self):
        """Create progress UI"""
        main_frame = ctk.CTkFrame(self, fg_color=self.theme_colors.bg)
        main_frame.pack(fill="both", expand=True)

        # Header
        header_frame = ctk.CTkFrame(main_frame, fg_color=self.theme_colors.surface, corner_radius=0)
        header_frame.pack(fill="x")

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=25, pady=20)

        if self.logo_image:
            icon = ctk.CTkLabel(header_inner, text="", image=self.logo_image)
            icon.pack(side="left", padx=(0, 15))
            for event_name in ("<Button-1>", "<Button-2>", "<Button-3>", "<Double-Button-1>"):
                icon.bind(event_name, lambda _event: "break")
        else:
            icon = ctk.CTkLabel(header_inner, text="⬇", font=ctk.CTkFont(size=36))
            icon.pack(side="left", padx=(0, 15))

        text_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        text_frame.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            text_frame,
            text="Download in Progress",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
            text_color=self.theme_colors.text_primary
        ).pack(anchor="w")

        self.queue_status_label = ctk.CTkLabel(
            text_frame,
            text="Preparing...",
            font=ctk.CTkFont(size=12),
            text_color=self.theme_colors.text_tertiary,
            anchor="w"
        )
        self.queue_status_label.pack(anchor="w")

        self.cancel_button = ctk.CTkButton(
            header_inner,
            text="Cancel Download",
            width=145,
            height=34,
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=self._handle_cancel
        )
        self.cancel_button.pack(side="right")

        # Content
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=25, pady=20)

        # Current item card
        item_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors.surface, corner_radius=12)
        item_card.pack(fill="x", pady=(0, 15))

        item_inner = ctk.CTkFrame(item_card, fg_color="transparent")
        item_inner.pack(fill="x", padx=18, pady=15)

        ctk.CTkLabel(
            item_inner,
            text="CURRENT ITEM",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.theme_colors.accent_blue
        ).pack(anchor="w")

        self.progress_label = ctk.CTkLabel(
            item_inner,
            text="Starting download...",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            wraplength=480,
            text_color=self.theme_colors.text_primary
        )
        self.progress_label.pack(anchor="w", pady=(5, 0))

        # Progress card
        progress_card = ctk.CTkFrame(content_frame, fg_color=self.theme_colors.surface, corner_radius=12)
        progress_card.pack(fill="x", pady=(0, 15))

        progress_inner = ctk.CTkFrame(progress_card, fg_color="transparent")
        progress_inner.pack(fill="x", padx=18, pady=15)

        progress_header = ctk.CTkFrame(progress_inner, fg_color="transparent")
        progress_header.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            progress_header,
            text="OVERALL PROGRESS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.theme_colors.accent_blue
        ).pack(side="left")

        self.percent_label = ctk.CTkLabel(
            progress_header,
            text="0%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.theme_colors.text_primary
        )
        self.percent_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            progress_inner,
            mode="determinate",
            height=16,
            corner_radius=8,
            fg_color=self.theme_colors.hover,
            progress_color=self.theme_colors.accent_blue
        )
        self.progress_bar.pack(fill="x", pady=(0, 12))
        self.progress_bar.set(0)

        # Stats
        stats_frame = ctk.CTkFrame(progress_inner, fg_color="transparent")
        stats_frame.pack(fill="x")

        self.speed_label, self.eta_label, self.size_label, self.total_size_label = self._create_stats(stats_frame)

        self.status_message = ctk.CTkLabel(
            content_frame,
            text="Please wait while your files are being downloaded...",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_tertiary
        )
        self.status_message.pack(pady=(5, 0))

    def _load_logo_image(self):
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ui', 'logo.png')
        if not os.path.exists(logo_path):
            return None
        try:
            image = Image.open(logo_path)
            return ctk.CTkImage(light_image=image, dark_image=image, size=(42, 42))
        except Exception:
            return None

    def _handle_cancel(self):
        if callable(self.on_cancel):
            self.on_cancel()

    def set_cancel_enabled(self, enabled: bool):
        self.cancel_button.configure(state="normal" if enabled else "disabled")

    def _create_stats(self, parent):
        """Create stats display"""
        parent.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="telemetry")

        speed_frame = ctk.CTkFrame(parent, fg_color="transparent")
        speed_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        ctk.CTkLabel(
            speed_frame,
            text="Speed",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_tertiary
        ).pack(anchor="w")

        speed_label = ctk.CTkLabel(
            speed_frame,
            text="--",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w"
        )
        speed_label.pack(anchor="w")

        eta_frame = ctk.CTkFrame(parent, fg_color="transparent")
        eta_frame.grid(row=0, column=1, sticky="nsew", padx=8)

        ctk.CTkLabel(
            eta_frame,
            text="Time Left",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_tertiary
        ).pack(anchor="w")

        eta_label = ctk.CTkLabel(
            eta_frame,
            text="--",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w"
        )
        eta_label.pack(anchor="w")

        size_frame = ctk.CTkFrame(parent, fg_color="transparent")
        size_frame.grid(row=0, column=2, sticky="nsew", padx=8)

        ctk.CTkLabel(
            size_frame,
            text="Downloaded",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_tertiary
        ).pack(anchor="w")

        size_label = ctk.CTkLabel(
            size_frame,
            text="0 B",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w"
        )
        size_label.pack(anchor="w")

        total_frame = ctk.CTkFrame(parent, fg_color="transparent")
        total_frame.grid(row=0, column=3, sticky="nsew", padx=(8, 0))

        ctk.CTkLabel(
            total_frame,
            text="Total Size",
            font=ctk.CTkFont(size=11),
            text_color=self.theme_colors.text_tertiary
        ).pack(anchor="w")

        total_size_label = ctk.CTkLabel(
            total_frame,
            text="--",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=self.theme_colors.text_primary,
            anchor="w"
        )
        total_size_label.pack(anchor="w")

        return speed_label, eta_label, size_label, total_size_label
