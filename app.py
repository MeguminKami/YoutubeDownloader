"""
Main application class
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import tempfile
from typing import List
import re
from PIL import Image
from core.models import DownloadItem
from core.deps import check_yt_dlp, get_missing_bundled_tools, is_frozen_runtime
from core.downloader import (
    Downloader,
    DownloadCancelledError,
    DirectDownloadError,
    MergeFailureError,
    MissingFFmpegError,
    NoCompatibleFormatError,
)
from ui.theme import ThemeManager
from ui.dialogs import InstallerDialog, OptionsDialog, ProgressDialog
from utils.format import format_bytes, format_speed, format_eta, SpeedSmoother

class YouTubeDownloaderApp(ctk.CTk):
    """Main application window"""

    def __init__(self):
        super().__init__()

        self.title("YouTube Downloader Pro")
        self.geometry("1024x768")
        self.minsize(800, 600)

        self.theme_manager = ThemeManager()
        self.theme_manager.register_callback(self._on_theme_change)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.download_queue: List[DownloadItem] = []
        self.current_download_widgets = []
        self.yt_dlp_available = False
        self._download_active = False
        self._cancel_requested = False
        self._session_created_files = set()
        self._download_folder = None
        self._logo_image = None
        self._window_icon = None
        self._window_icon_ico = None

        self._load_brand_assets()

        self._apply_theme()
        self.create_widgets()

        self.after(100, self._check_dependencies)

    def _apply_theme(self):
        """Apply current theme colors"""
        self.colors = self.theme_manager.get_colors()
        self.configure(fg_color=self.colors.bg)

    def _load_brand_assets(self):
        """Load official logo assets used by the application UI."""
        logo_path = os.path.join(os.path.dirname(__file__), 'ui', 'logo.png')
        if not os.path.exists(logo_path):
            return

        try:
            logo_image = Image.open(logo_path)
            self._logo_image = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(56, 56))
        except Exception:
            self._logo_image = None

        try:
            # tkinter iconphoto expects PhotoImage, so keep a dedicated Tk photo object.
            import tkinter as tk
            self._window_icon = tk.PhotoImage(file=logo_path)
            self.iconphoto(True, self._window_icon)
        except Exception:
            self._window_icon = None

        # Windows title bar/taskbar icon is usually driven by ICO files.
        try:
            ico_path = os.path.join(os.path.dirname(__file__), 'ui', 'logo.ico')
            if not os.path.exists(ico_path):
                ico_path = os.path.join(tempfile.gettempdir(), 'youtube_downloader_logo.ico')
                with Image.open(logo_path) as icon_source:
                    icon_source.save(ico_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
            self._window_icon_ico = ico_path
            self.iconbitmap(self._window_icon_ico)
        except Exception:
            self._window_icon_ico = None

    def _on_theme_change(self, colors):
        """Handle theme change"""
        self.colors = colors
        self.configure(fg_color=colors.bg)
        # Recreate widgets with new colors
        for widget in self.winfo_children():
            widget.destroy()
        self.current_download_widgets.clear()
        self.create_widgets()

    def create_widgets(self):
        """Create all UI widgets"""
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Header with title and theme toggle
        header_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))

        title_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_container.pack(side="left", fill="x", expand=True)

        title_row = ctk.CTkFrame(title_container, fg_color="transparent")
        title_row.pack(anchor="center")

        if self._logo_image:
            logo_label = ctk.CTkLabel(
                title_row,
                text="",
                image=self._logo_image,
                fg_color="transparent",
                bg_color="transparent",
                cursor="arrow"
            )
            logo_label.pack(side="left", padx=(0, 12))
            for event_name in ("<Button-1>", "<Button-2>", "<Button-3>", "<Double-Button-1>"):
                logo_label.bind(event_name, lambda _event: "break")

        title = ctk.CTkLabel(
            title_row,
            text="YouTube Downloader Pro",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=self.colors.accent_blue
        )
        title.pack(side="left")

        subtitle = ctk.CTkLabel(
            title_container,
            text="Download videos and audio with ease",
            font=ctk.CTkFont(size=14),
            text_color=self.colors.text_tertiary,
            anchor="center"
        )
        subtitle.pack(anchor="center")

        # Theme toggle switch
        theme_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        theme_frame.pack(side="right")

        theme_label = ctk.CTkLabel(
            theme_frame,
            text="🌙" if self.theme_manager.is_dark() else "☀️",
            font=ctk.CTkFont(size=20)
        )
        theme_label.pack(side="left", padx=(0, 10))

        theme_switch = ctk.CTkSwitch(
            theme_frame,
            text="",
            command=self.theme_manager.toggle,
            width=50
        )
        theme_switch.pack(side="left")
        if not self.theme_manager.is_dark():
            theme_switch.select()

        # URL Input Section
        input_frame = ctk.CTkFrame(main_container, fg_color=self.colors.surface, corner_radius=15)
        input_frame.pack(fill="x", pady=(0, 20))

        input_inner = ctk.CTkFrame(input_frame, fg_color="transparent")
        input_inner.pack(fill="x", padx=20, pady=20)

        input_label = ctk.CTkLabel(
            input_inner,
            text="Enter YouTube URL",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors.text_primary
        )
        input_label.pack(anchor="w", pady=(0, 10))

        url_container = ctk.CTkFrame(input_inner, fg_color="transparent")
        url_container.pack(fill="x")

        self.url_entry = ctk.CTkEntry(
            url_container,
            placeholder_text="https://youtube.com/watch?v=...",
            height=45,
            font=ctk.CTkFont(size=13),
            corner_radius=10
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        paste_btn = ctk.CTkButton(
            url_container,
            text="Paste",
            width=80,
            height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10,
            fg_color="#4a5568",
            hover_color="#2d3748",
            command=self.paste_url
        )
        paste_btn.pack(side="left", padx=(0, 10))

        add_btn = ctk.CTkButton(
            url_container,
            text="Add to Queue",
            width=140,
            height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10,
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            command=self.add_to_queue
        )
        add_btn.pack(side="left")

        # Queue Section
        queue_frame = ctk.CTkFrame(main_container, fg_color=self.colors.surface, corner_radius=15)
        queue_frame.pack(fill="both", expand=True, pady=(0, 20))

        queue_header = ctk.CTkFrame(queue_frame, fg_color="transparent")
        queue_header.pack(fill="x", padx=20, pady=(20, 10))

        queue_label = ctk.CTkLabel(
            queue_header,
            text="Download Queue",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=self.colors.text_primary
        )
        queue_label.pack(side="left")

        self.queue_count = ctk.CTkLabel(
            queue_header,
            text="0 items",
            font=ctk.CTkFont(size=13),
            text_color=self.colors.text_tertiary
        )
        self.queue_count.pack(side="right")

        self.queue_scroll = ctk.CTkScrollableFrame(
            queue_frame,
            fg_color="transparent",
            corner_radius=10
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.empty_state = ctk.CTkLabel(
            self.queue_scroll,
            text="No items in queue.\nAdd a YouTube URL to get started",
            font=ctk.CTkFont(size=14),
            text_color=self.colors.text_tertiary
        )
        self.empty_state.pack(pady=40)

        # Download Button
        download_btn = ctk.CTkButton(
            main_container,
            text="Download All",
            height=55,
            font=ctk.CTkFont(size=18, weight="bold"),
            corner_radius=15,
            fg_color=self.colors.accent_purple,
            command=self.start_download
        )
        download_btn.pack(fill="x")

    def _check_dependencies(self):
        """Check if yt-dlp is installed"""
        if is_frozen_runtime():
            missing_tools = get_missing_bundled_tools()
            if missing_tools:
                missing_text = ', '.join(missing_tools)
                messagebox.showerror(
                    "Packaging Error",
                    (
                        "This release bundle is missing required runtime tools:\n"
                        f"{missing_text}\n\n"
                        "Please download a complete release package or contact support."
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
            return

        if check_yt_dlp():
            self.yt_dlp_available = True
        else:
            self._show_installer()

    def _show_installer(self):
        """Show installer dialog"""
        if is_frozen_runtime():
            messagebox.showerror(
                "Packaging Error",
                "Runtime dependency installation is disabled in packaged builds. Please use a complete release bundle.",
            )
            self.quit()
            return

        def on_success():
            self.yt_dlp_available = True
            messagebox.showinfo("Success", "yt-dlp installed successfully!")

        def on_failure():
            messagebox.showerror(
                "Installation Failed",
                "Could not install yt-dlp.\n\nPlease install manually:\npip install yt-dlp"
            )
            self.quit()

        InstallerDialog(self, self.colors, on_success, on_failure)

    def paste_url(self):
        """Paste URL from clipboard"""
        try:
            clipboard_content = self.clipboard_get()
            self.url_entry.delete(0, 'end')
            self.url_entry.insert(0, clipboard_content)
        except:
            pass

    def is_valid_youtube_url(self, url: str) -> bool:
        """Simple validation for YouTube URLs (watch, short, playlist, shorts)"""
        if not url or not isinstance(url, str):
            return False

        # Accept common YouTube URL forms:
        # - https://www.youtube.com/watch?v=...
        # - https://youtu.be/...
        # - https://www.youtube.com/playlist?list=...
        # - https://www.youtube.com/shorts/...
        pattern = re.compile(
            r'^(?:https?://)?(?:www\.)?(?:m\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)(?:/|$)',
            re.IGNORECASE
        )
        return bool(pattern.search(url.strip()))

    def _split_sentences_per_line(self, text: str) -> str:
        """Return readable popup text with one sentence per line."""
        if not text:
            return "Unknown error."

        normalized = ' '.join(str(text).replace('\r', ' ').replace('\n', ' ').split())
        normalized = re.sub(r'^ERROR:\s*', '', normalized, flags=re.IGNORECASE)

        # Convert sentence boundaries to line breaks while keeping URLs intact.
        normalized = re.sub(r'(?<=[.!?])\s+', '\n', normalized)
        return normalized.strip() if normalized.strip() else "Unknown error."

    def _format_processing_error(self, raw_error: str) -> str:
        """Map common yt-dlp extraction failures to clear user instructions."""
        lower = (raw_error or '').lower()
        if "sign in to confirm you're not a bot" in lower or "sign in to confirm you\u2019re not a bot" in lower:
            return "\n".join([
                "YouTube asked for account verification before allowing this request.",
                "Export fresh browser cookies and save them to cookies.txt in this app folder.",
                "Restart the app and try this URL again.",
            ])

        return self._split_sentences_per_line(raw_error)

    def add_to_queue(self):
        """Add URL to download queue"""
        if not self.yt_dlp_available:
            messagebox.showerror("Error", "yt-dlp is not installed")
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL")
            return

        # Validate pasted/entered URL before proceeding
        if not self.is_valid_youtube_url(url):
            messagebox.showerror("Invalid URL", "The pasted text is not a valid YouTube URL.\n\nPlease paste a YouTube video/playlist URL and try again.")
            # Re-enable/focus entry so user can correct
            try:
                self.url_entry.configure(state="normal")
                self.url_entry.focus_set()
            except:
                pass
            return

        self.url_entry.configure(state="disabled")
        thread = threading.Thread(target=self.process_url, args=(url,))
        thread.daemon = True
        thread.start()

    def process_url(self, url):
        """Process URL and show options dialog"""
        try:
            downloader = Downloader()
            info = downloader.extract_info(url)
            self.after(0, lambda: self.show_options_dialog(url, info))
        except Exception as e:
            formatted_error = self._format_processing_error(str(e))
            self.after(0, lambda msg=formatted_error: messagebox.showerror("Error Processing URL", msg))
        finally:
            self.after(0, lambda: self.url_entry.configure(state="normal"))

    def show_options_dialog(self, url, info):
        """Show options dialog"""
        def callback(items):
            if items:
                for item in items:
                    self.download_queue.append(item)
                self.update_queue_display()
                self.url_entry.delete(0, 'end')
            self.url_entry.configure(state="normal")

        OptionsDialog(self, self.colors, url, info, callback)

    def update_queue_display(self):
        """Update queue display"""
        for widget in self.current_download_widgets:
            widget.destroy()
        self.current_download_widgets.clear()

        if len(self.download_queue) == 0:
            self.empty_state.pack(pady=40)
        else:
            self.empty_state.pack_forget()

        self.queue_count.configure(text=f"{len(self.download_queue)} items")

        for idx, item in enumerate(self.download_queue):
            item_frame = ctk.CTkFrame(
                self.queue_scroll,
                fg_color=self.colors.hover,
                corner_radius=10
            )
            item_frame.pack(fill="x", pady=5)
            self.current_download_widgets.append(item_frame)

            inner_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            inner_frame.pack(fill="x", padx=15, pady=12)

            info_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True)

            icon = "🎬" if item.item_type == "video" else "🎵"
            title = ctk.CTkLabel(
                info_frame,
                text=f"{icon} {item.title[:60]}..." if len(item.title) > 60 else f"{icon} {item.title}",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=self.colors.text_primary
            )
            title.pack(anchor="w")

            if item.item_type == "video":
                # Use quality_label for display, fallback to quality/height
                quality_display = item.quality_label or (f"{item.height}p" if item.height else "Auto")
                details_text = f"{quality_display} - MP4"
                if getattr(item, 'requires_merge', False):
                    details_text += " (auto audio merge)"
            else:
                details_text = f"MP3 {item.audio_format} kbps"

            if item.is_playlist:
                details_text += " - Playlist"
                if item.merge_playlist:
                    details_text += " (merged)"

            details = ctk.CTkLabel(
                info_frame,
                text=details_text,
                font=ctk.CTkFont(size=11),
                text_color=self.colors.text_tertiary
            )
            details.pack(anchor="w", pady=(2, 0))

            remove_btn = ctk.CTkButton(
                inner_frame,
                text="✕",
                width=35,
                height=35,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="#ef4444",
                hover_color="#dc2626",
                corner_radius=8,
                command=lambda i=idx: self.remove_from_queue(i)
            )
            remove_btn.pack(side="right")

    def remove_from_queue(self, index):
        """Remove item from queue"""
        if 0 <= index < len(self.download_queue):
            self.download_queue.pop(index)
            self.update_queue_display()

    def start_download(self):
        """Start downloading all items"""
        if self._download_active:
            messagebox.showinfo("Download Running", "A download is already in progress.")
            return

        if len(self.download_queue) == 0:
            messagebox.showinfo("Info", "No items in queue to download")
            return

        folder = filedialog.askdirectory(title="Select Download Folder")
        if not folder:
            return

        thread = threading.Thread(target=self.download_all, args=(folder,))
        thread.daemon = True
        thread.start()

    def _snapshot_files(self, folder: str) -> set:
        """Capture all current files under target folder for cancellation cleanup."""
        paths = set()
        if not folder or not os.path.isdir(folder):
            return paths
        for root, _, files in os.walk(folder):
            for name in files:
                paths.add(os.path.abspath(os.path.join(root, name)))
        return paths

    def _delete_session_files(self):
        """Delete files produced during the current session when user cancels."""
        for file_path in sorted(self._session_created_files, reverse=True):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception:
                pass

        self._session_created_files.clear()

    def _request_cancel_download(self):
        """Ask current worker to stop and keep queue untouched for retry."""
        if not self._download_active:
            return
        self._cancel_requested = True
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.after(0, lambda: self.progress_dialog.status_message.configure(text="Cancelling download... cleaning files."))
            self.after(0, lambda: self.progress_dialog.set_cancel_enabled(False))

    def _is_cancel_requested(self) -> bool:
        return bool(self._cancel_requested)

    def _total_size_text(self) -> str:
        """Return a user-friendly total size text for progress labels."""
        if getattr(self, 'total_estimated_bytes', None):
            return format_bytes(self.total_estimated_bytes)
        if getattr(self, '_estimating_size', False):
            return "Estimating..."
        return "Unknown"

    def _update_queue_status_label(self, current: int, total: int):
        """Display clear queue progress like 'Download x/total' plus total size."""
        text = f"Download {current}/{total}  |  Total size: {self._total_size_text()}"
        self.after(0, lambda t=text: self.progress_dialog.queue_status_label.configure(text=t))

    def download_all(self, folder):
        """Download all queued items with progress tracking"""
        self._download_active = True
        self._cancel_requested = False
        self._session_created_files = set()
        self._download_folder = folder

        # Show progress dialog first (on main thread)
        self.progress_dialog = None
        self._dialog_ready = threading.Event()
        self.after(0, self._show_progress_dialog)

        # Wait for dialog to be created
        self._dialog_ready.wait(timeout=5)

        if self.progress_dialog is None:
            self._download_active = False
            self._cancel_requested = False
            self.after(0, lambda: messagebox.showerror("Error", "Could not create progress dialog"))
            return

        downloader = Downloader()
        total_items = len(self.download_queue)
        self.current_total_items = total_items
        self._estimating_size = True

        # Update status: Estimating size
        self.after(0, lambda: self.progress_dialog.status_message.configure(text="Estimating download size..."))
        self._update_queue_status_label(0, total_items)
        self.after(0, lambda: self.progress_dialog.total_size_label.configure(text="Estimating..."))

        # Estimate total size for all items
        total_estimated_size = 0
        for item in self.download_queue:
            if self._cancel_requested:
                break
            try:
                size = downloader.estimate_size(item.url, item.item_type, item.quality, item.audio_format)
                if size:
                    item.estimated_size = size
                    total_estimated_size += size
            except:
                pass

        self.total_estimated_bytes = total_estimated_size if total_estimated_size > 0 else None
        self._estimating_size = False
        self.completed_bytes = 0
        self.current_item_bytes = 0
        self.speed_smoother = SpeedSmoother()

        # Update total size label
        if self.total_estimated_bytes:
            self.after(0, lambda sz=format_bytes(self.total_estimated_bytes):
                      self.progress_dialog.total_size_label.configure(text=sz))
        else:
            self.after(0, lambda: self.progress_dialog.total_size_label.configure(text="Unknown"))

        self._update_queue_status_label(0, total_items)

        # Download each item
        cancelled = False
        had_errors = False
        for idx, item in enumerate(self.download_queue):
            if self._cancel_requested:
                cancelled = True
                break

            try:
                self.current_item_index = idx
                self.current_item_bytes = 0
                before_item_files = self._snapshot_files(folder)

                # Update UI for current item
                file_num = idx + 1
                self._update_queue_status_label(file_num, total_items)
                self.after(0, lambda title=item.title:
                          self.progress_dialog.progress_label.configure(text=title[:50] + "..." if len(title) > 50 else title))
                self.after(0, lambda i=file_num, t=total_items:
                          self.progress_dialog.status_message.configure(text=f"Downloading selected quality... (Download {i}/{t})"))

                def progress_hook(d):
                    self._handle_progress(d, item)

                downloader.download_item(item, folder, progress_hook, should_cancel=self._is_cancel_requested)

                after_item_files = self._snapshot_files(folder)
                self._session_created_files.update(after_item_files - before_item_files)

                # Mark item as complete - add its size to completed bytes
                if item.estimated_size:
                    self.completed_bytes += item.estimated_size
                else:
                    # If no estimate, approximate from last downloaded bytes
                    self.completed_bytes += self.current_item_bytes

            except Exception as e:
                if isinstance(e, DownloadCancelledError):
                    cancelled = True
                    break

                had_errors = True
                if isinstance(e, MissingFFmpegError):
                    error_title = "FFmpeg Required"
                elif isinstance(e, NoCompatibleFormatError):
                    error_title = "No Compatible Format"
                elif isinstance(e, MergeFailureError):
                    error_title = "Merge Failed"
                elif isinstance(e, DirectDownloadError):
                    error_title = "Direct Download Failed"
                else:
                    error_title = "Download Error"

                self.after(0, lambda err=str(e), i=idx, title=error_title:
                          messagebox.showerror(title, f"Error downloading item {i+1}:\n{err}"))

        if cancelled:
            self._delete_session_files()

        self.after(0, lambda c=cancelled, e=had_errors: self._download_complete(cancelled=c, had_errors=e))

    def _handle_progress(self, d, item):
        """Handle progress updates from yt-dlp"""
        if d.get('status') == 'stage':
            stage = d.get('stage', '')
            stage_map = {
                'fetching formats': 'Fetching formats...',
                'formats loaded': 'Formats loaded',
                'downloading selected quality': 'Downloading selected quality...',
                'downloading video stream': 'Downloading video stream...',
                'downloading audio stream': 'Downloading audio stream...',
                'merging streams': 'Merging streams...',
                'completed': 'Completed',
            }
            status_text = stage_map.get(stage, stage)
            current = min(getattr(self, 'current_item_index', 0) + 1, getattr(self, 'current_total_items', 1))
            total = max(1, getattr(self, 'current_total_items', 1))
            self.after(0, lambda t=status_text, c=current, total_items=total:
                      self.progress_dialog.status_message.configure(text=f"{t} (Download {c}/{total_items})"))
            return

        if d['status'] == 'downloading':
            try:
                if d.get('percent') is not None:
                    percent = max(0.0, min(100.0, float(d.get('percent', 0))))
                    self.after(0, lambda p=percent:
                              self.progress_dialog.percent_label.configure(text=f"{p:.1f}%"))
                    self.after(0, lambda p=percent / 100:
                              self.progress_dialog.progress_bar.set(p))

                    speed_text = d.get('speed_text') or "--"
                    eta_text = d.get('eta_text') or "--"
                    self.after(0, lambda s=speed_text:
                              self.progress_dialog.speed_label.configure(text=s))
                    self.after(0, lambda e=eta_text:
                              self.progress_dialog.eta_label.configure(text=e))
                    return

                downloaded = d.get('downloaded_bytes') or 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                speed = d.get('speed') or 0

                # yt-dlp may report None for unknown values during startup.
                downloaded = float(downloaded) if downloaded else 0
                total = float(total) if total else 0
                speed = float(speed) if speed else 0

                # Update current item bytes (monotonic)
                if downloaded > self.current_item_bytes:
                    self.current_item_bytes = downloaded

                # Calculate overall progress
                if self.total_estimated_bytes and self.total_estimated_bytes > 0:
                    overall_bytes = self.completed_bytes + self.current_item_bytes
                    overall_percent = (overall_bytes / self.total_estimated_bytes) * 100
                    overall_percent = min(100, overall_percent)

                    # Smooth speed and calculate ETA
                    if speed:
                        smoothed_speed = self.speed_smoother.update(speed)
                        remaining_bytes = self.total_estimated_bytes - overall_bytes
                        eta_seconds = remaining_bytes / smoothed_speed if smoothed_speed > 0 else 0
                    else:
                        smoothed_speed = 0
                        eta_seconds = 0

                    self.after(0, lambda p=overall_percent:
                              self.progress_dialog.percent_label.configure(text=f"{p:.1f}%"))
                    self.after(0, lambda p=overall_percent/100:
                              self.progress_dialog.progress_bar.set(p))
                    self.after(0, lambda s=format_speed(smoothed_speed if smoothed_speed else speed):
                              self.progress_dialog.speed_label.configure(text=s))
                    self.after(0, lambda e=format_eta(eta_seconds):
                              self.progress_dialog.eta_label.configure(text=e))
                    self.after(0, lambda sz=format_bytes(overall_bytes):
                              self.progress_dialog.size_label.configure(text=sz))
                else:
                    # Fallback: per-file progress
                    if total:
                        percent = (downloaded / total) * 100
                        self.after(0, lambda p=percent:
                                  self.progress_dialog.percent_label.configure(text=f"{p:.1f}%"))
                        self.after(0, lambda p=percent/100:
                                  self.progress_dialog.progress_bar.set(p))

                    self.after(0, lambda s=format_speed(speed):
                              self.progress_dialog.speed_label.configure(text=s))
                    self.after(0, lambda e=format_eta(d.get('eta', 0)):
                              self.progress_dialog.eta_label.configure(text=e))
                    self.after(0, lambda sz=format_bytes(downloaded):
                              self.progress_dialog.size_label.configure(text=sz))

            except Exception as ex:
                print(f"Progress hook error: {ex}")

        elif d['status'] == 'finished':
            current = min(getattr(self, 'current_item_index', 0) + 1, getattr(self, 'current_total_items', 1))
            total = max(1, getattr(self, 'current_total_items', 1))
            self.after(0, lambda c=current, total_items=total:
                      self.progress_dialog.status_message.configure(text=f"Processing file... (Download {c}/{total_items})"))

    def _show_progress_dialog(self):
        """Show progress dialog"""
        self.progress_dialog = ProgressDialog(self, self.colors, on_cancel=self._request_cancel_download)
        self.progress_dialog.update()  # Force UI update
        if hasattr(self, '_dialog_ready'):
            self._dialog_ready.set()

    def _download_complete(self, cancelled: bool = False, had_errors: bool = False):
        """Handle download completion"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.destroy()
            self.progress_dialog = None

        self._download_active = False
        self._cancel_requested = False
        self._download_folder = None

        if cancelled:
            messagebox.showinfo("Cancelled", "Download cancelled. Queue kept so you can retry.")
            self.update_queue_display()
            return

        if had_errors:
            messagebox.showwarning("Completed with Errors", "Download finished, but some items failed.")
            self.download_queue.clear()
            self.update_queue_display()
            return

        messagebox.showinfo("Complete", "All downloads completed successfully!")
        self.download_queue.clear()
        self.update_queue_display()
