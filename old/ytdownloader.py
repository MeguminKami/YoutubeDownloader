"""
Modern YouTube Downloader
A feature-rich application for downloading YouTube videos and audio with playlist support
"""

import customtkinter as ctk
import yt_dlp
import threading
import os
from pathlib import Path
from tkinter import filedialog, messagebox
import json
from PIL import Image
import io
import sys
import ctypes
import subprocess
import shutil
import glob
import re

def is_admin():
    """Check if the script is running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """Re-run the script with admin privileges"""
    if sys.platform == 'win32':
        # Get the path to the Python executable and the script
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])

        # Use ShellExecuteW to run with elevated privileges
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}" {params}',
            None,
            1  # SW_SHOWNORMAL
        )
        sys.exit(0)

class DownloadItem:
    """Represents a single download item in the queue"""
    def __init__(self, url, item_type="video", quality=None, audio_format=None, is_playlist=False, merge_playlist=False, custom_name=None):
        self.url = url
        self.item_type = item_type  # "video" or "audio"
        self.quality = quality
        self.audio_format = audio_format
        self.is_playlist = is_playlist
        self.merge_playlist = merge_playlist
        self.custom_name = custom_name
        self.title = "Loading..."
        self.status = "Pending"

class YouTubeDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("YouTube Downloader Pro")
        self.geometry("1280x960")
        self.minsize(800, 600)

        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Download queue
        self.download_queue = []
        self.current_download_widgets = []

        # Colors
        self.bg_color = "#1a1a1a"
        self.card_color = "#2b2b2b"
        self.hover_color = "#3a3a3a"
        self.accent_color = "#00d26a"

        self.configure(fg_color=self.bg_color)

        self.create_widgets()

    def create_widgets(self):
        """Create all UI widgets"""

        # Main container with padding
        # Chupa
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_frame = ctk.CTkFrame(main_container, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 20))

        title = ctk.CTkLabel(
            title_frame,
            text="🎬 YouTube Downloader Pro",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=self.accent_color
        )
        title.pack()

        subtitle = ctk.CTkLabel(
            title_frame,
            text="Download videos and audio with ease",
            font=ctk.CTkFont(size=14),
            text_color="#888888"
        )
        subtitle.pack()

        # URL Input Section
        input_frame = ctk.CTkFrame(main_container, fg_color=self.card_color, corner_radius=15)
        input_frame.pack(fill="x", pady=(0, 20))

        input_inner = ctk.CTkFrame(input_frame, fg_color="transparent")
        input_inner.pack(fill="x", padx=20, pady=20)

        input_label = ctk.CTkLabel(
            input_inner,
            text="Enter YouTube URL",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        input_label.pack(anchor="w", pady=(0, 10))

        url_input_container = ctk.CTkFrame(input_inner, fg_color="transparent")
        url_input_container.pack(fill="x")

        self.url_entry = ctk.CTkEntry(
            url_input_container,
            placeholder_text="https://youtube.com/watch?v=...",
            height=45,
            font=ctk.CTkFont(size=13),
            corner_radius=10
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Paste button with symbol
        paste_btn = ctk.CTkButton(
            url_input_container,
            text="📋",
            width=45,
            height=45,
            font=ctk.CTkFont(size=20),
            corner_radius=10,
            fg_color=self.hover_color,
            hover_color=self.card_color,
            command=self.paste_url
        )
        paste_btn.pack(side="left", padx=(0, 10))
        self.create_tooltip(paste_btn, "Paste from clipboard")

        # Add button
        add_btn = ctk.CTkButton(
            url_input_container,
            text="Add to Queue",
            width=140,
            height=45,
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10,
            fg_color="#0066cc",
            hover_color="#0052a3",
            command=self.add_to_queue
        )
        add_btn.pack(side="left")

        # Download Queue Section
        queue_frame = ctk.CTkFrame(main_container, fg_color=self.card_color, corner_radius=15)
        queue_frame.pack(fill="both", expand=True, pady=(0, 20))

        queue_header = ctk.CTkFrame(queue_frame, fg_color="transparent")
        queue_header.pack(fill="x", padx=20, pady=(20, 10))

        queue_label = ctk.CTkLabel(
            queue_header,
            text="Download Queue",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        queue_label.pack(side="left")

        self.queue_count = ctk.CTkLabel(
            queue_header,
            text="0 items",
            font=ctk.CTkFont(size=13),
            text_color="#888888"
        )
        self.queue_count.pack(side="right")

        # Scrollable frame for download items
        self.queue_scroll = ctk.CTkScrollableFrame(
            queue_frame,
            fg_color="transparent",
            corner_radius=10
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Empty state
        self.empty_state = ctk.CTkLabel(
            self.queue_scroll,
            text="No items in queue.\nAdd a YouTube URL to get started",
            font=ctk.CTkFont(size=14),
            text_color="#666666"
        )
        self.empty_state.pack(pady=40)

        # Download Button
        download_btn = ctk.CTkButton(
            main_container,
            text="⬇ Download All",
            height=55,
            font=ctk.CTkFont(size=18, weight="bold"),
            corner_radius=15,
            fg_color=self.accent_color,
            hover_color="#00b359",
            command=self.start_download
        )
        download_btn.pack(fill="x")

    def create_tooltip(self, widget, text):
        """Create hover tooltip for widget"""
        def on_enter(event):
            tooltip = ctk.CTkToplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

            label = ctk.CTkLabel(
                tooltip,
                text=text,
                fg_color=self.card_color,
                corner_radius=8,
                padx=10,
                pady=5
            )
            label.pack()

            widget.tooltip = tooltip

        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                delattr(widget, 'tooltip')

        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)

    def paste_url(self):
        """Paste URL from clipboard"""
        try:
            clipboard_content = self.clipboard_get()
            self.url_entry.delete(0, 'end')
            self.url_entry.insert(0, clipboard_content)
        except:
            pass

    def add_to_queue(self):
        """Add URL to download queue with options dialog"""
        url = self.url_entry.get().strip()

        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL")
            return

        # Show loading
        self.url_entry.configure(state="disabled")

        # Run in thread to avoid freezing
        thread = threading.Thread(target=self.process_url, args=(url,))
        thread.daemon = True
        thread.start()

    def process_url(self, url):
        """Process URL and show options dialog"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            # Schedule UI update in main thread
            self.after(0, lambda: self.show_options_dialog(url, info))

        except Exception as e:
            self.after(0, lambda: self.show_error(f"Error processing URL: {str(e)}"))
            self.after(0, lambda: self.url_entry.configure(state="normal"))

    def show_options_dialog(self, url, info):
        """Show dialog to configure download options"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Download Options")
        dialog.geometry("600x700")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (700 // 2)
        dialog.geometry(f"+{x}+{y}")

        # Main container frame
        container = ctk.CTkFrame(dialog, fg_color=self.bg_color)
        container.pack(fill="both", expand=True)

        # Scrollable frame for options
        scroll_frame = ctk.CTkScrollableFrame(container, fg_color=self.bg_color)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=(20, 10))

        # Title
        is_playlist = 'entries' in info
        title_text = info.get('title', 'Unknown')

        title = ctk.CTkLabel(
            scroll_frame,
            text=title_text[:60] + "..." if len(title_text) > 60 else title_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            wraplength=550
        )
        title.pack(pady=(0, 10))

        if is_playlist:
            playlist_count = len(info['entries'])
            count_label = ctk.CTkLabel(
                scroll_frame,
                text=f"Playlist with {playlist_count} videos",
                font=ctk.CTkFont(size=13),
                text_color=self.accent_color
            )
            count_label.pack(pady=(0, 20))

        # Download type
        type_frame = ctk.CTkFrame(scroll_frame, fg_color=self.card_color, corner_radius=10)
        type_frame.pack(fill="x", pady=(0, 15))
        type_inner = ctk.CTkFrame(type_frame, fg_color="transparent")
        type_inner.pack(fill="x", padx=15, pady=15)

        type_label = ctk.CTkLabel(
            type_inner,
            text="Download Type",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        type_label.pack(anchor="w", pady=(0, 10))

        download_type = ctk.StringVar(value="video")

        video_radio = ctk.CTkRadioButton(
            type_inner,
            text="Video (MP4)",
            variable=download_type,
            value="video",
            font=ctk.CTkFont(size=13)
        )
        video_radio.pack(anchor="w", pady=2)

        audio_radio = ctk.CTkRadioButton(
            type_inner,
            text="Audio Only (MP3)",
            variable=download_type,
            value="audio",
            font=ctk.CTkFont(size=13)
        )
        audio_radio.pack(anchor="w", pady=2)

        # Playlist options
        merge_playlist_var = None
        custom_name_entry = None

        if is_playlist:
            playlist_frame = ctk.CTkFrame(scroll_frame, fg_color=self.card_color, corner_radius=10)
            playlist_frame.pack(fill="x", pady=(0, 15))
            playlist_inner = ctk.CTkFrame(playlist_frame, fg_color="transparent")
            playlist_inner.pack(fill="x", padx=15, pady=15)

            playlist_label = ctk.CTkLabel(
                playlist_inner,
                text="Playlist Options",
                font=ctk.CTkFont(size=14, weight="bold")
            )
            playlist_label.pack(anchor="w", pady=(0, 10))

            merge_playlist_var = ctk.StringVar(value="separate")

            separate_radio = ctk.CTkRadioButton(
                playlist_inner,
                text="Download each video separately",
                variable=merge_playlist_var,
                value="separate",
                font=ctk.CTkFont(size=13)
            )
            separate_radio.pack(anchor="w", pady=2)

            merge_radio = ctk.CTkRadioButton(
                playlist_inner,
                text="Merge all into one file",
                variable=merge_playlist_var,
                value="merge",
                font=ctk.CTkFont(size=13)
            )
            merge_radio.pack(anchor="w", pady=2)

            # Custom name for merged file
            name_label = ctk.CTkLabel(
                playlist_inner,
                text="Custom name (for merged file):",
                font=ctk.CTkFont(size=12),
                text_color="#888888"
            )
            name_label.pack(anchor="w", pady=(10, 5))

            custom_name_entry = ctk.CTkEntry(
                playlist_inner,
                placeholder_text="Leave empty to use playlist name",
                height=35,
                font=ctk.CTkFont(size=12)
            )
            custom_name_entry.pack(fill="x", pady=(0, 5))

        # Video Quality selection frame
        video_quality_frame = ctk.CTkFrame(scroll_frame, fg_color=self.card_color, corner_radius=10)
        video_quality_frame.pack(fill="x", pady=(0, 15))
        video_quality_inner = ctk.CTkFrame(video_quality_frame, fg_color="transparent")
        video_quality_inner.pack(fill="x", padx=15, pady=15)

        video_quality_label = ctk.CTkLabel(
            video_quality_inner,
            text="Video Quality",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        video_quality_label.pack(anchor="w", pady=(0, 10))

        quality_var = ctk.StringVar(value="best")

        qualities = [
            ("Best Available", "best"),
            ("1080p (Full HD)", "1080"),
            ("720p (HD)", "720"),
            ("480p (SD)", "480"),
            ("360p (Low)", "360")
        ]

        for qual_name, qual_value in qualities:
            radio = ctk.CTkRadioButton(
                video_quality_inner,
                text=qual_name,
                variable=quality_var,
                value=qual_value,
                font=ctk.CTkFont(size=12)
            )
            radio.pack(anchor="w", pady=2)

        # Audio Quality selection frame
        audio_quality_frame = ctk.CTkFrame(scroll_frame, fg_color=self.card_color, corner_radius=10)
        audio_quality_inner = ctk.CTkFrame(audio_quality_frame, fg_color="transparent")
        audio_quality_inner.pack(fill="x", padx=15, pady=15)

        audio_quality_label = ctk.CTkLabel(
            audio_quality_inner,
            text="Audio Quality",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        audio_quality_label.pack(anchor="w", pady=(0, 10))

        audio_quality_var = ctk.StringVar(value="192")

        audio_qualities = [
            ("High (320 kbps)", "320"),
            ("Medium (192 kbps)", "192"),
            ("Low (128 kbps)", "128")
        ]

        for qual_name, qual_value in audio_qualities:
            radio = ctk.CTkRadioButton(
                audio_quality_inner,
                text=qual_name,
                variable=audio_quality_var,
                value=qual_value,
                font=ctk.CTkFont(size=12)
            )
            radio.pack(anchor="w", pady=2)

        # Function to toggle visibility based on download type
        def on_type_change(*args):
            if download_type.get() == "video":
                video_quality_frame.pack(fill="x", pady=(0, 15))
                audio_quality_frame.pack_forget()
            else:
                video_quality_frame.pack_forget()
                audio_quality_frame.pack(fill="x", pady=(0, 15))

        download_type.trace_add("write", on_type_change)
        # Initialize visibility
        on_type_change()

        # Buttons - in a separate fixed frame at the bottom
        btn_frame = ctk.CTkFrame(container, fg_color=self.bg_color)
        btn_frame.pack(fill="x", padx=20, pady=(10, 20))

        def on_add():
            merge = merge_playlist_var.get() == "merge" if merge_playlist_var else False
            custom_name = custom_name_entry.get().strip() if custom_name_entry else None

            item = DownloadItem(
                url=url,
                item_type=download_type.get(),
                quality=quality_var.get(),
                audio_format=audio_quality_var.get(),  # Now stores audio bitrate
                is_playlist=is_playlist,
                merge_playlist=merge,
                custom_name=custom_name if custom_name else None
            )

            # Get title for display
            if is_playlist and merge:
                item.title = custom_name if custom_name else info.get('title', 'Playlist')
            else:
                item.title = info.get('title', 'Unknown')

            self.download_queue.append(item)
            self.update_queue_display()

            dialog.destroy()
            self.url_entry.delete(0, 'end')
            self.url_entry.configure(state="normal")

        def on_cancel():
            dialog.destroy()
            self.url_entry.configure(state="normal")

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=140,
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color="#666666",
            hover_color="#555555",
            command=on_cancel
        )
        cancel_btn.pack(side="left", padx=(0, 10))

        add_btn = ctk.CTkButton(
            btn_frame,
            text="Add to Queue",
            width=200,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=self.accent_color,
            hover_color="#00b359",
            command=on_add
        )
        add_btn.pack(side="right")

    def update_queue_display(self):
        """Update the download queue display"""
        # Clear existing widgets
        for widget in self.current_download_widgets:
            widget.destroy()
        self.current_download_widgets.clear()

        # Hide/show empty state
        if len(self.download_queue) == 0:
            self.empty_state.pack(pady=40)
        else:
            self.empty_state.pack_forget()

        # Update count
        self.queue_count.configure(text=f"{len(self.download_queue)} items")

        # Create item widgets
        for idx, item in enumerate(self.download_queue):
            item_frame = ctk.CTkFrame(
                self.queue_scroll,
                fg_color=self.hover_color,
                corner_radius=10
            )
            item_frame.pack(fill="x", pady=5)
            self.current_download_widgets.append(item_frame)

            inner_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
            inner_frame.pack(fill="x", padx=15, pady=12)

            # Left side: info
            info_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="x", expand=True)

            # Icon and title
            title_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            title_frame.pack(anchor="w")

            icon = "Video" if item.item_type == "video" else "Audio"
            title = ctk.CTkLabel(
                title_frame,
                text=f"[{icon}] {item.title[:60]}..." if len(item.title) > 60 else f"[{icon}] {item.title}",
                font=ctk.CTkFont(size=13, weight="bold")
            )
            title.pack(side="left")

            # Details
            if item.item_type == "video":
                if item.quality == "best":
                    details_text = "Best Quality - MP4"
                else:
                    details_text = f"{item.quality}p - MP4"
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
                text_color="#888888"
            )
            details.pack(anchor="w", pady=(2, 0))

            # Right side: remove button
            remove_btn = ctk.CTkButton(
                inner_frame,
                text="X",
                width=35,
                height=35,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="#cc0000",
                hover_color="#990000",
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
        """Start downloading all items in queue"""
        if len(self.download_queue) == 0:
            messagebox.showinfo("Info", "No items in queue to download")
            return

        # Ask for download folder
        folder = filedialog.askdirectory(title="Select Download Folder")
        if not folder:
            return

        # Start download in thread
        thread = threading.Thread(target=self.download_all, args=(folder,))
        thread.daemon = True
        thread.start()

    def download_all(self, folder):
        """Download all queued items"""
        self.after(0, lambda: self.show_progress_dialog())
        total_items = len(self.download_queue)

        # Track overall progress
        self.total_items = total_items
        self.completed_items = 0
        self.current_item_progress = 0

        for idx, item in enumerate(self.download_queue):
            try:
                self.current_item_index = idx
                self.after(0, lambda i=idx, t=total_items: self.update_queue_status(i+1, t))
                self.after(0, lambda it=item: self.update_progress(it.title))
                self.after(0, lambda: self.update_status_message("Downloading..."))

                # Update overall progress (completed items + 0% of current)
                overall_percent = (self.completed_items / self.total_items) * 100
                self.after(0, lambda p=overall_percent: self.update_percent(f"{p:.1f}%"))
                self.after(0, lambda p=overall_percent/100: self.update_progress_bar(p))

                # Configure yt-dlp options
                ydl_opts = {
                    'outtmpl': os.path.join(folder, '%(title)s.%(ext)s'),
                    'quiet': False,
                    'no_warnings': False,
                    'progress_hooks': [self.progress_hook],
                }

                # Track temp folder for playlist merging
                temp_folder = None

                if item.item_type == "audio":
                    # Download audio and convert to MP3 (most compatible format)
                    ydl_opts['format'] = 'bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': item.audio_format,  # This is now the bitrate (128, 192, 320)
                    }]
                else:
                    # Download video as MP4 (most compatible format)
                    if item.quality == "best":
                        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                    else:
                        ydl_opts['format'] = f'bestvideo[height<={item.quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={item.quality}][ext=mp4]/best[height<={item.quality}]'

                    ydl_opts['merge_output_format'] = 'mp4'

                # Handle playlist merging
                if item.is_playlist and item.merge_playlist:
                    # Download all videos to temp folder first
                    temp_folder = os.path.join(folder, f'temp_playlist_{idx}')
                    os.makedirs(temp_folder, exist_ok=True)

                    ydl_opts['outtmpl'] = os.path.join(temp_folder, '%(playlist_index)03d - %(title)s.%(ext)s')

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([item.url])

                # Mark this item as complete
                self.completed_items += 1

                # Merge playlist files if needed
                if item.is_playlist and item.merge_playlist and temp_folder:
                    self.after(0, lambda: self.update_status_message("Merging playlist files..."))
                    self.after(0, lambda: self.update_progress("Merging all files into one..."))

                    # Determine output extension
                    if item.item_type == "audio":
                        ext = "mp3"
                    else:
                        ext = "mp4"

                    # Get the output filename
                    output_name = item.custom_name if item.custom_name else item.title
                    # Sanitize filename
                    output_name = re.sub(r'[<>:"/\\|?*]', '_', output_name)
                    output_file = os.path.join(folder, f"{output_name}.{ext}")

                    # Merge the files
                    success = self.merge_playlist_files(temp_folder, output_file, ext)

                    if success:
                        # Clean up temp folder
                        self.after(0, lambda: self.update_status_message("Cleaning up temporary files..."))
                        try:
                            shutil.rmtree(temp_folder)
                        except Exception as e:
                            print(f"Warning: Could not delete temp folder: {e}")

                self.after(0, lambda i=idx: self.mark_complete(i))

            except Exception as e:
                self.completed_items += 1  # Still count as processed
                self.after(0, lambda i=idx, err=str(e): self.mark_error(i, err))
                # Try to clean up temp folder on error
                if temp_folder and os.path.exists(temp_folder):
                    try:
                        shutil.rmtree(temp_folder)
                    except:
                        pass

        self.after(0, lambda: self.download_complete())

    def merge_playlist_files(self, temp_folder, output_file, ext):
        """Merge all downloaded files in temp folder into one file using FFmpeg"""
        try:
            # Get all files in temp folder, sorted by name (which includes playlist index)
            if ext == 'mp3':
                patterns = ['*.mp3']
            else:
                patterns = ['*.mp4']

            files = []
            for pattern in patterns:
                files.extend(glob.glob(os.path.join(temp_folder, pattern)))

            # Sort files by name to maintain playlist order
            files.sort()

            if not files:
                raise Exception("No files found to merge")

            # Create a file list for FFmpeg concat
            list_file = os.path.join(temp_folder, 'filelist.txt')
            with open(list_file, 'w', encoding='utf-8') as f:
                for file in files:
                    # Escape single quotes in filename for FFmpeg
                    escaped_path = file.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            # Run FFmpeg to concatenate files
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Overwrite output file
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',  # Copy streams without re-encoding (fast)
                output_file
            ]

            # Try with stream copy first, if it fails, re-encode
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            if result.returncode != 0:
                # If copy failed, try re-encoding
                if ext == 'mp3':
                    # Audio re-encode to MP3
                    ffmpeg_cmd = [
                        'ffmpeg',
                        '-y',
                        '-f', 'concat',
                        '-safe', '0',
                        '-i', list_file,
                        '-acodec', 'libmp3lame',
                        '-b:a', '192k',
                        output_file
                    ]
                else:
                    # Video re-encode to MP4
                    ffmpeg_cmd = [
                        'ffmpeg',
                        '-y',
                        '-f', 'concat',
                        '-safe', '0',
                        '-i', list_file,
                        '-c:v', 'libx264',
                        '-c:a', 'aac',
                        '-preset', 'fast',
                        output_file
                    ]

                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )

                if result.returncode != 0:
                    raise Exception(f"FFmpeg error: {result.stderr}")

            return True

        except Exception as e:
            self.after(0, lambda err=str(e): messagebox.showerror("Merge Error", f"Failed to merge files: {err}"))
            return False

    def progress_hook(self, d):
        """Hook for download progress"""
        if d['status'] == 'downloading':
            try:
                # Get current file progress (0-100)
                current_file_percent = 0
                if d.get('total_bytes'):
                    current_file_percent = d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100
                elif d.get('total_bytes_estimate'):
                    current_file_percent = d.get('downloaded_bytes', 0) / d.get('total_bytes_estimate', 1) * 100

                # Calculate overall progress: completed items + fraction of current item
                if hasattr(self, 'total_items') and self.total_items > 0:
                    overall_percent = ((self.completed_items + (current_file_percent / 100)) / self.total_items) * 100
                else:
                    overall_percent = current_file_percent

                percent_str = f"{overall_percent:.1f}%"

                # Get speed in readable format
                speed_bytes = d.get('speed', 0)
                if speed_bytes:
                    if speed_bytes >= 1024 * 1024:
                        speed_str = f"{speed_bytes / (1024 * 1024):.1f} MB/s"
                    elif speed_bytes >= 1024:
                        speed_str = f"{speed_bytes / 1024:.1f} KB/s"
                    else:
                        speed_str = f"{speed_bytes:.0f} B/s"
                else:
                    speed_str = "--"

                # Get ETA in readable format
                eta_seconds = d.get('eta', 0)
                if eta_seconds:
                    if eta_seconds >= 3600:
                        eta_str = f"{eta_seconds // 3600}h {(eta_seconds % 3600) // 60}m"
                    elif eta_seconds >= 60:
                        eta_str = f"{eta_seconds // 60}m {eta_seconds % 60}s"
                    else:
                        eta_str = f"{eta_seconds}s"
                else:
                    eta_str = "--"

                # Get downloaded size in readable format (for current file)
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0

                if downloaded_bytes >= 1024 * 1024 * 1024:
                    downloaded_str = f"{downloaded_bytes / (1024 * 1024 * 1024):.2f} GB"
                elif downloaded_bytes >= 1024 * 1024:
                    downloaded_str = f"{downloaded_bytes / (1024 * 1024):.1f} MB"
                elif downloaded_bytes >= 1024:
                    downloaded_str = f"{downloaded_bytes / 1024:.1f} KB"
                else:
                    downloaded_str = f"{downloaded_bytes} B"

                if total_bytes:
                    if total_bytes >= 1024 * 1024 * 1024:
                        total_str = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"
                    elif total_bytes >= 1024 * 1024:
                        total_str = f"{total_bytes / (1024 * 1024):.1f} MB"
                    elif total_bytes >= 1024:
                        total_str = f"{total_bytes / 1024:.1f} KB"
                    else:
                        total_str = f"{total_bytes} B"
                    size_str = f"{downloaded_str} / {total_str}"
                else:
                    size_str = downloaded_str

                # Update all progress UI elements
                self.after(0, lambda p=percent_str: self.update_percent(p))
                self.after(0, lambda s=speed_str: self.update_speed(s))
                self.after(0, lambda e=eta_str: self.update_eta(e))
                self.after(0, lambda sz=size_str: self.update_size(sz))
                self.after(0, lambda pct=overall_percent/100: self.update_progress_bar(pct))

            except Exception as ex:
                print(f"Progress hook error: {ex}")
                pass
        elif d['status'] == 'finished':
            self.after(0, lambda: self.update_status_message("Processing file..."))

    def update_progress_bar(self, value):
        """Update progress bar with actual value (0.0 to 1.0)"""
        if hasattr(self, 'progress_bar') and self.progress_bar:
            try:
                # Switch to determinate mode if not already
                if self.progress_bar.cget("mode") == "indeterminate":
                    self.progress_bar.stop()
                    self.progress_bar.configure(mode="determinate")
                # Clamp value between 0 and 1
                value = max(0.0, min(1.0, value))
                self.progress_bar.set(value)
            except Exception as e:
                print(f"Progress bar update error: {e}")

    def update_percent(self, percent):
        """Update percent label"""
        if hasattr(self, 'percent_label') and self.percent_label:
            try:
                self.percent_label.configure(text=percent)
            except:
                pass

    def update_speed(self, speed):
        """Update speed label"""
        if hasattr(self, 'speed_label') and self.speed_label:
            try:
                self.speed_label.configure(text=speed if speed else '--')
            except:
                pass

    def update_eta(self, eta):
        """Update ETA label"""
        if hasattr(self, 'eta_label') and self.eta_label:
            try:
                self.eta_label.configure(text=eta if eta else '--')
            except:
                pass

    def update_size(self, size):
        """Update size label"""
        if hasattr(self, 'size_label') and self.size_label:
            try:
                self.size_label.configure(text=size if size else '--')
            except:
                pass

    def update_status_message(self, message):
        """Update status message"""
        if hasattr(self, 'status_message') and self.status_message:
            try:
                self.status_message.configure(text=message)
            except:
                pass

    def update_queue_status(self, current, total):
        """Update queue status in header"""
        if hasattr(self, 'queue_status_label') and self.queue_status_label:
            try:
                self.queue_status_label.configure(text=f"Processing {current} of {total} items")
            except:
                pass

    def update_progress(self, text):
        """Update progress label with current item title"""
        if hasattr(self, 'progress_label') and self.progress_label:
            try:
                self.progress_label.configure(text=text)
            except:
                pass

    def show_progress_dialog(self):
        """Show progress dialog with download information"""
        self.progress_dialog = ctk.CTkToplevel(self)
        self.progress_dialog.title("Downloading...")
        self.progress_dialog.geometry("550x400")
        self.progress_dialog.resizable(False, False)
        self.progress_dialog.transient(self)
        self.progress_dialog.grab_set()
        self.progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        # Center dialog
        self.progress_dialog.update_idletasks()
        x = (self.progress_dialog.winfo_screenwidth() // 2) - (550 // 2)
        y = (self.progress_dialog.winfo_screenheight() // 2) - (400 // 2)
        self.progress_dialog.geometry(f"+{x}+{y}")

        # Main container
        main_frame = ctk.CTkFrame(self.progress_dialog, fg_color=self.bg_color)
        main_frame.pack(fill="both", expand=True)

        # Header with icon
        header_frame = ctk.CTkFrame(main_frame, fg_color=self.card_color, corner_radius=0)
        header_frame.pack(fill="x")

        header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_inner.pack(fill="x", padx=25, pady=20)

        download_icon = ctk.CTkLabel(
            header_inner,
            text="⬇",
            font=ctk.CTkFont(size=36)
        )
        download_icon.pack(side="left", padx=(0, 15))

        header_text_frame = ctk.CTkFrame(header_inner, fg_color="transparent")
        header_text_frame.pack(side="left", fill="x", expand=True)

        header_title = ctk.CTkLabel(
            header_text_frame,
            text="Download in Progress",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w"
        )
        header_title.pack(anchor="w")

        self.queue_status_label = ctk.CTkLabel(
            header_text_frame,
            text="Preparing...",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
            anchor="w"
        )
        self.queue_status_label.pack(anchor="w")

        # Content area
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=25, pady=20)

        # Current item card
        item_card = ctk.CTkFrame(content_frame, fg_color=self.card_color, corner_radius=12)
        item_card.pack(fill="x", pady=(0, 15))

        item_inner = ctk.CTkFrame(item_card, fg_color="transparent")
        item_inner.pack(fill="x", padx=18, pady=15)

        current_label = ctk.CTkLabel(
            item_inner,
            text="CURRENT ITEM",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.accent_color
        )
        current_label.pack(anchor="w")

        self.progress_label = ctk.CTkLabel(
            item_inner,
            text="Starting download...",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            wraplength=480
        )
        self.progress_label.pack(anchor="w", pady=(5, 0))

        # Progress bar section
        progress_card = ctk.CTkFrame(content_frame, fg_color=self.card_color, corner_radius=12)
        progress_card.pack(fill="x", pady=(0, 15))

        progress_inner = ctk.CTkFrame(progress_card, fg_color="transparent")
        progress_inner.pack(fill="x", padx=18, pady=15)

        # Progress header with percentage
        progress_header = ctk.CTkFrame(progress_inner, fg_color="transparent")
        progress_header.pack(fill="x", pady=(0, 8))

        progress_title = ctk.CTkLabel(
            progress_header,
            text="DOWNLOAD PROGRESS",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=self.accent_color
        )
        progress_title.pack(side="left")

        self.percent_label = ctk.CTkLabel(
            progress_header,
            text="0%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff"
        )
        self.percent_label.pack(side="right")

        # Progress bar - determinate mode from start
        self.progress_bar = ctk.CTkProgressBar(
            progress_inner,
            mode="determinate",
            height=16,
            corner_radius=8,
            fg_color=self.hover_color,
            progress_color=self.accent_color
        )
        self.progress_bar.pack(fill="x", pady=(0, 12))
        self.progress_bar.set(0)

        # Stats row
        stats_frame = ctk.CTkFrame(progress_inner, fg_color="transparent")
        stats_frame.pack(fill="x")

        # Speed stat
        speed_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        speed_frame.pack(side="left", expand=True)

        ctk.CTkLabel(
            speed_frame,
            text="Speed",
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        ).pack(anchor="w")

        self.speed_label = ctk.CTkLabel(
            speed_frame,
            text="--",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.speed_label.pack(anchor="w")

        # ETA stat
        eta_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        eta_frame.pack(side="left", expand=True)

        ctk.CTkLabel(
            eta_frame,
            text="Time Left",
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        ).pack(anchor="w")

        self.eta_label = ctk.CTkLabel(
            eta_frame,
            text="--",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.eta_label.pack(anchor="w")

        # Size stat
        size_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
        size_frame.pack(side="left", expand=True)

        ctk.CTkLabel(
            size_frame,
            text="Downloaded",
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        ).pack(anchor="w")

        self.size_label = ctk.CTkLabel(
            size_frame,
            text="0 B / 0 B",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.size_label.pack(anchor="w")

        # Status message
        self.status_message = ctk.CTkLabel(
            content_frame,
            text="Please wait while your files are being downloaded...",
            font=ctk.CTkFont(size=11),
            text_color="#666666"
        )
        self.status_message.pack(pady=(5, 0))

    def mark_complete(self, index):
        """Mark item as complete"""
        pass  # Could update UI to show checkmark

    def mark_error(self, index, error):
        """Mark item as error"""
        messagebox.showerror("Download Error", f"Error downloading item {index+1}:\n{error}")

    def download_complete(self):
        """Called when all downloads complete"""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.destroy()

        messagebox.showinfo("Complete", "All downloads completed successfully!")

        # Clear queue
        self.download_queue.clear()
        self.update_queue_display()

    def show_error(self, message):
        """Show error message"""
        messagebox.showerror("Error", message)
        self.url_entry.configure(state="normal")

if __name__ == "__main__":
    # Check for admin privileges
    if not is_admin():
        run_as_admin()

    app = YouTubeDownloaderApp()
    app.mainloop()
