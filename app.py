"""
Main application class
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
from typing import List
import re
from core.models import DownloadItem
from core.deps import check_yt_dlp
from core.downloader import (
    Downloader,
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

        self._apply_theme()
        self.create_widgets()

        self.after(100, self._check_dependencies)

    def _apply_theme(self):
        """Apply current theme colors"""
        self.colors = self.theme_manager.get_colors()
        self.configure(fg_color=self.colors.bg)

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

        title = ctk.CTkLabel(
            title_container,
            text="🎬 YouTube Downloader Pro",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=self.colors.accent_blue
        )
        title.pack()

        subtitle = ctk.CTkLabel(
            title_container,
            text="Download videos and audio with ease",
            font=ctk.CTkFont(size=14),
            text_color=self.colors.text_tertiary
        )
        subtitle.pack()

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
            text="⬇ Download All",
            height=55,
            font=ctk.CTkFont(size=18, weight="bold"),
            corner_radius=15,
            fg_color=self.colors.accent_purple,
            command=self.start_download
        )
        download_btn.pack(fill="x")

    def _check_dependencies(self):
        """Check if yt-dlp is installed"""
        if check_yt_dlp():
            self.yt_dlp_available = True
        else:
            self._show_installer()

    def _show_installer(self):
        """Show installer dialog"""
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
            self.after(0, lambda: messagebox.showerror("Error", f"Error processing URL: {str(e)}"))
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
        if len(self.download_queue) == 0:
            messagebox.showinfo("Info", "No items in queue to download")
            return

        folder = filedialog.askdirectory(title="Select Download Folder")
        if not folder:
            return

        thread = threading.Thread(target=self.download_all, args=(folder,))
        thread.daemon = True
        thread.start()

    def download_all(self, folder):
        """Download all queued items with progress tracking"""

        # Show progress dialog first (on main thread)
        self.progress_dialog = None
        self._dialog_ready = threading.Event()
        self.after(0, self._show_progress_dialog)

        # Wait for dialog to be created
        self._dialog_ready.wait(timeout=5)

        if self.progress_dialog is None:
            self.after(0, lambda: messagebox.showerror("Error", "Could not create progress dialog"))
            return

        downloader = Downloader()
        total_items = len(self.download_queue)

        # Update status: Estimating size
        self.after(0, lambda: self.progress_dialog.status_message.configure(text="Estimating download size..."))
        self.after(0, lambda: self.progress_dialog.queue_status_label.configure(text=f"0 of {total_items} files"))

        # Estimate total size for all items
        total_estimated_size = 0
        for item in self.download_queue:
            try:
                size = downloader.estimate_size(item.url, item.item_type, item.quality, item.audio_format)
                if size:
                    item.estimated_size = size
                    total_estimated_size += size
            except:
                pass

        self.total_estimated_bytes = total_estimated_size if total_estimated_size > 0 else None
        self.completed_bytes = 0
        self.current_item_bytes = 0
        self.speed_smoother = SpeedSmoother()

        # Update total size label
        if self.total_estimated_bytes:
            self.after(0, lambda sz=format_bytes(self.total_estimated_bytes):
                      self.progress_dialog.total_size_label.configure(text=sz))

        # Download each item
        for idx, item in enumerate(self.download_queue):
            try:
                self.current_item_index = idx
                self.current_item_bytes = 0

                # Update UI for current item
                file_num = idx + 1
                self.after(0, lambda i=file_num, t=total_items:
                          self.progress_dialog.queue_status_label.configure(text=f"File {i} of {t}"))
                self.after(0, lambda title=item.title:
                          self.progress_dialog.progress_label.configure(text=title[:50] + "..." if len(title) > 50 else title))
                self.after(0, lambda:
                          self.progress_dialog.status_message.configure(text="Downloading selected quality..."))

                def progress_hook(d):
                    self._handle_progress(d, item)

                downloader.download_item(item, folder, progress_hook)

                # Mark item as complete - add its size to completed bytes
                if item.estimated_size:
                    self.completed_bytes += item.estimated_size
                else:
                    # If no estimate, approximate from last downloaded bytes
                    self.completed_bytes += self.current_item_bytes

            except Exception as e:
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

        self.after(0, self._download_complete)

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
            self.after(0, lambda t=status_text: self.progress_dialog.status_message.configure(text=t))
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
            self.after(0, lambda:
                      self.progress_dialog.status_message.configure(text="Processing file..."))

    def _show_progress_dialog(self):
        """Show progress dialog"""
        self.progress_dialog = ProgressDialog(self, self.colors)
        self.progress_dialog.update()  # Force UI update
        if hasattr(self, '_dialog_ready'):
            self._dialog_ready.set()

    def _download_complete(self):
        """Handle download completion"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.destroy()

        messagebox.showinfo("Complete", "All downloads completed successfully!")
        self.download_queue.clear()
        self.update_queue_display()
