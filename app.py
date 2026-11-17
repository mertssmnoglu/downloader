import re
import threading
from tkinter import filedialog, messagebox, StringVar

import customtkinter as ctk

from config import config
from youtube import DownloadOptions, Quality, MediaType
from youtube.ytdlp import YtDlpDownloader, format_bytes, format_duration


YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?((www|m|music)\.)?"
    r"(youtube\.com/(watch\?.*v=[\w-]+|shorts/[\w-]+|live/[\w-]+|embed/[\w-]+)"
    r"|youtu\.be/[\w-]+)",
    re.IGNORECASE,
)

VK_URL_PATTERN = re.compile(
    r"^(https?://)?((www|m)\.)?"
    r"(vkvideo\.ru|vk\.com|vk\.ru)/"
    r"(video|clip)-?\d+_\d+",
    re.IGNORECASE,
)

ODYSEE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?"
    r"odysee\.com/"
    r"(?:\$/(?:embed|download)/)?"
    r"(?:@[^/\s]+/)?"
    r"[^/\s?#]+",
    re.IGNORECASE,
)


class UI:
    """
    UI Components Container
    """

    link_entry: ctk.CTkEntry
    select_folder_button: ctk.CTkButton
    download_button: ctk.CTkButton
    status_label: ctk.CTkLabel
    path_label: ctk.CTkLabel
    path_frame: ctk.CTkFrame
    audio_button: ctk.CTkButton
    video_button: ctk.CTkButton
    video_quality_frame: ctk.CTkFrame
    quality_row_high: ctk.CTkFrame
    quality_row_low: ctk.CTkFrame
    video_quality_buttons: dict
    video_quality_var: StringVar
    selected_media_type: str
    info_frame: ctk.CTkFrame
    info_title: ctk.CTkLabel
    info_meta: ctk.CTkLabel
    progress_bar: ctk.CTkProgressBar


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YouTube İndirici")
        self.geometry("640x600")
        self.resizable(True, True)

        self.downloader = YtDlpDownloader()
        self._video_info = None
        self._last_url = ""
        self._info_job_id = 0
        self._debounce_id = None
        self._downloading = False

        self.ui = UI()
        self.__setup_ui(self.ui)

        self.klasor = config.get_download_path()
        self._update_path_display()

    def __setup_ui(self, ui: UI):
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        ui.link_entry = ctk.CTkEntry(self, placeholder_text="YouTube linki yapıştır")
        ui.link_entry.pack(pady=(20, 8), padx=20, fill="x")
        ui.link_entry.bind("<KeyRelease>", self._on_link_changed)
        ui.link_entry.bind("<<Paste>>", self._on_link_changed)
        ui.link_entry.bind("<FocusOut>", self._on_link_changed)
        ui.link_entry.bind("<Return>", self._on_link_changed)

        ui.info_frame = ctk.CTkFrame(self)
        ui.info_frame.pack(pady=5, padx=20, fill="x")

        ui.info_title = ctk.CTkLabel(
            ui.info_frame,
            text="Geçerli bir link yapıştırın",
            anchor="w",
            justify="left",
            wraplength=580,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        ui.info_title.pack(padx=12, pady=(10, 2), fill="x")

        ui.info_meta = ctk.CTkLabel(
            ui.info_frame,
            text="Süre, boyut ve çözünürlük burada görünür.",
            anchor="w",
            justify="left",
            wraplength=580,
            text_color="gray",
        )
        ui.info_meta.pack(padx=12, pady=(0, 10), fill="x")

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=5, padx=20, fill="x")

        ui.audio_button = ctk.CTkButton(
            button_frame,
            text="Ses (MP3)",
            command=self.set_audio_mode,
            fg_color="#1f6aa5",
            width=150,
        )
        ui.audio_button.pack(side="left", padx=5, expand=True, fill="x")

        ui.video_button = ctk.CTkButton(
            button_frame,
            text="Video (MP4)",
            command=self.set_video_mode,
            fg_color="#3a3a3a",
            width=150,
        )
        ui.video_button.pack(side="left", padx=5, expand=True, fill="x")
        ui.selected_media_type = MediaType.AUDIO

        ui.video_quality_var = StringVar(value=Quality.VIDEO_1080P)
        ui.video_quality_var.trace_add("write", self._on_quality_changed)
        ui.video_quality_frame = ctk.CTkFrame(self)
        ui.video_quality_frame.pack(pady=5, padx=20, fill="x")

        quality_label = ctk.CTkLabel(
            ui.video_quality_frame, text="Kalite:", anchor="w"
        )
        quality_label.pack(padx=10, pady=(8, 2), fill="x")

        ui.quality_row_high = ctk.CTkFrame(ui.video_quality_frame, fg_color="transparent")
        ui.quality_row_high.pack(fill="x", padx=4, pady=(0, 2))
        ui.quality_row_low = ctk.CTkFrame(ui.video_quality_frame, fg_color="transparent")
        ui.quality_row_low.pack(fill="x", padx=4, pady=(0, 6))

        ui.video_quality_buttons = {}
        for quality in Quality.HIGH_ROW:
            button = ctk.CTkButton(
                ui.quality_row_high,
                text=quality,
                width=70,
                command=lambda q=quality: self.set_video_quality(q),
            )
            button.pack(side="left", padx=4, pady=4, expand=True, fill="x")
            ui.video_quality_buttons[quality] = button
        for quality in Quality.LOW_ROW:
            button = ctk.CTkButton(
                ui.quality_row_low,
                text=quality,
                width=70,
                command=lambda q=quality: self.set_video_quality(q),
            )
            button.pack(side="left", padx=4, pady=4, expand=True, fill="x")
            ui.video_quality_buttons[quality] = button
        self._highlight_quality_buttons()
        ui.video_quality_frame.pack_forget()

        ui.path_frame = ctk.CTkFrame(self)
        ui.path_frame.pack(pady=10, padx=20, fill="x")

        self.ui.path_label = ctk.CTkLabel(
            ui.path_frame, text="", text_color="gray", anchor="w"
        )
        self.ui.path_label.pack(side="left", padx=10, fill="x", expand=True)

        self.ui.select_folder_button = ctk.CTkButton(
            ui.path_frame, text="📁 Değiştir", command=self.klasor_sec, width=100
        )
        self.ui.select_folder_button.pack(side="right", padx=5)

        self.ui.download_button = ctk.CTkButton(
            self, text="İndir", command=self.download_media
        )
        self.ui.download_button.pack(pady=10)

        ui.progress_bar = ctk.CTkProgressBar(self)
        ui.progress_bar.set(0)

        self.ui.status_label = ctk.CTkLabel(self, text="")
        self.ui.status_label.pack(pady=5)

    def klasor_sec(self):
        initial_dir = config.get_download_path()
        self.klasor = filedialog.askdirectory(initialdir=initial_dir)
        if self.klasor:
            self.ui.status_label.configure(text="Klasör seçildi")
            self._update_path_display()

    def _update_path_display(self):
        """Update the path label to show current download location."""
        if self.klasor:
            display_path = self.klasor
            if len(display_path) > 50:
                display_path = "..." + display_path[-47:]
            self.ui.path_label.configure(text=f"📁 {display_path}")

    def set_audio_mode(self):
        self.ui.selected_media_type = MediaType.AUDIO
        self.ui.audio_button.configure(fg_color="#1f6aa5")
        self.ui.video_button.configure(fg_color="#3a3a3a")
        self.ui.video_quality_frame.pack_forget()
        self._refresh_info_panel()

    def set_video_mode(self):
        self.ui.selected_media_type = MediaType.VIDEO
        self.ui.audio_button.configure(fg_color="#3a3a3a")
        self.ui.video_button.configure(fg_color="#1f6aa5")
        self.ui.video_quality_frame.pack(
            pady=5, padx=20, fill="x", before=self.ui.path_frame
        )
        self._update_quality_availability()
        self._refresh_info_panel()

    def set_video_quality(self, quality: str):
        estimate = ((self._video_info or {}).get("estimates") or {}).get(quality) or {}
        if self._video_info and not estimate.get("available", True):
            return
        self.ui.video_quality_var.set(quality)
        self._highlight_quality_buttons()

    def _quality_is_available(self, quality: str) -> bool:
        if not self._video_info:
            return True
        estimate = (self._video_info.get("estimates") or {}).get(quality) or {}
        return bool(estimate.get("available"))

    def _best_available_quality(self) -> str | None:
        for quality in Quality.VIDEO_CHOICES:
            if self._quality_is_available(quality):
                return quality
        return None

    def _update_quality_availability(self):
        show_high = False
        show_low = False
        for quality in Quality.HIGH_ROW:
            visible = self._quality_is_available(quality)
            self._set_quality_button_visible(quality, visible)
            show_high = show_high or visible
        for quality in Quality.LOW_ROW:
            visible = self._quality_is_available(quality)
            self._set_quality_button_visible(quality, visible)
            show_low = show_low or visible

        self.ui.quality_row_high.pack_forget()
        self.ui.quality_row_low.pack_forget()
        if show_high:
            self.ui.quality_row_high.pack(fill="x", padx=4, pady=(0, 2))
        if show_low:
            self.ui.quality_row_low.pack(fill="x", padx=4, pady=(0, 6))

        selected = self.ui.video_quality_var.get()
        if self._video_info and not self._quality_is_available(selected):
            fallback = self._best_available_quality()
            if fallback:
                self.ui.video_quality_var.set(fallback)

        self._highlight_quality_buttons()

    def _set_quality_button_visible(self, quality: str, visible: bool):
        button = self.ui.video_quality_buttons[quality]
        if visible:
            button.pack(side="left", padx=4, pady=4, expand=True, fill="x")
        else:
            button.pack_forget()

    def _highlight_quality_buttons(self):
        selected = self.ui.video_quality_var.get()
        for quality, button in self.ui.video_quality_buttons.items():
            button.configure(
                fg_color="#1f6aa5" if quality == selected else "#3a3a3a"
            )

    def _on_quality_changed(self, *_args):
        self._highlight_quality_buttons()
        self._refresh_info_panel()

    def _on_link_changed(self, _event=None):
        if self._downloading:
            return
        if self._debounce_id is not None:
            self.after_cancel(self._debounce_id)
        self._debounce_id = self.after(400, self._process_link)

    def _is_valid_youtube_url(self, url: str) -> bool:
        url = url.strip()
        return bool(
            url
            and (
                YOUTUBE_URL_PATTERN.search(url)
                or VK_URL_PATTERN.search(url)
                or ODYSEE_URL_PATTERN.search(url)
            )
        )

    def _process_link(self):
        url = self.ui.link_entry.get().strip()
        if not self._is_valid_youtube_url(url):
            if url != self._last_url:
                self._clear_info()
            return

        if url == self._last_url and self._video_info:
            self._refresh_info_panel()
            return

        self._info_job_id += 1
        job_id = self._info_job_id
        self.ui.info_title.configure(text="Bilgiler alınıyor...")
        self.ui.info_meta.configure(text="Video süresi ve boyutu hazırlanıyor.")
        self.ui.status_label.configure(text="Video bilgisi çekiliyor...")

        thread = threading.Thread(
            target=self._fetch_info_worker, args=(url, job_id), daemon=True
        )
        thread.start()

    def _fetch_info_worker(self, url: str, job_id: int):
        try:
            info = self.downloader.get_video_info(url)
            self.after(0, lambda: self._apply_video_info(info, url, job_id))
        except Exception as exc:
            self.after(0, lambda: self._apply_info_error(str(exc), url, job_id))

    def _show_progress_bar(self):
        if self.ui.progress_bar.winfo_ismapped():
            return
        self.ui.progress_bar.pack(
            pady=(0, 5), padx=20, fill="x", before=self.ui.status_label
        )

    def _hide_progress_bar(self):
        self.ui.progress_bar.stop()
        self.ui.progress_bar.configure(mode="determinate")
        self.ui.progress_bar.set(0)
        self.ui.progress_bar.pack_forget()

    def _stop_info_progress(self):
        if self._downloading:
            return
        self._hide_progress_bar()

    def _apply_video_info(self, info: dict, url: str, job_id: int):
        if job_id != self._info_job_id:
            return
        self._stop_info_progress()
        self._video_info = info
        self._last_url = url
        if not self._downloading:
            self.ui.status_label.configure(text="")
        self._update_quality_availability()
        self._refresh_info_panel()

    def _apply_info_error(self, error: str, url: str, job_id: int):
        if job_id != self._info_job_id:
            return
        self._stop_info_progress()
        self._video_info = None
        self._last_url = url
        self.ui.info_title.configure(text="Video bilgisi alınamadı")
        self.ui.info_meta.configure(text=error)
        self._update_quality_availability()
        if not self._downloading:
            self.ui.status_label.configure(text="❌ Geçersiz veya erişilemeyen link")

    def _clear_info(self):
        self._video_info = None
        self._last_url = ""
        self.ui.info_title.configure(text="Geçerli bir link yapıştırın")
        self.ui.info_meta.configure(text="Süre, boyut ve çözünürlük burada görünür.")
        self._update_quality_availability()
        if not self._downloading:
            self.ui.status_label.configure(text="")

    def _current_estimate(self) -> dict | None:
        if not self._video_info:
            return None
        estimates = self._video_info.get("estimates") or {}
        if self.ui.selected_media_type == MediaType.AUDIO:
            return estimates.get(MediaType.AUDIO)
        return estimates.get(self.ui.video_quality_var.get())

    def _refresh_info_panel(self):
        if not self._video_info:
            return

        title = self._video_info.get("title") or "Başlıksız"
        duration = format_duration(self._video_info.get("duration"))
        estimate = self._current_estimate() or {}
        size_text = format_bytes(estimate.get("bytes"), bool(estimate.get("exact")))

        if self.ui.selected_media_type == MediaType.AUDIO:
            extra = estimate.get("resolution") or "MP3"
            meta = f"Süre: {duration}   •   Boyut: {size_text}   •   {extra}"
        else:
            selected = self.ui.video_quality_var.get()
            if not estimate.get("available", True):
                meta = f"Süre: {duration}   •   {selected} bu videoda yok"
            else:
                resolution = estimate.get("resolution") or selected
                meta = f"Süre: {duration}   •   Boyut: {size_text}   •   {resolution}"

        self.ui.info_title.configure(text=title)
        self.ui.info_meta.configure(text=meta)

    def _set_controls_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.ui.download_button.configure(state=state)
        self.ui.link_entry.configure(state=state)
        self.ui.select_folder_button.configure(state=state)
        self.ui.audio_button.configure(state=state)
        self.ui.video_button.configure(state=state)
        if enabled:
            self._update_quality_availability()
        else:
            for button in self.ui.video_quality_buttons.values():
                button.configure(state=state)

    def download_media(self) -> None:
        link = self.ui.link_entry.get().strip()
        if not link:
            messagebox.showwarning("Eksik Bilgi", "Lütfen link girin.")
            return
        if not self._is_valid_youtube_url(link):
            messagebox.showwarning("Eksik Bilgi", "Lütfen geçerli bir YouTube linki girin.")
            return
        if (
            self.ui.selected_media_type == MediaType.VIDEO
            and self._video_info
            and not self._quality_is_available(self.ui.video_quality_var.get())
        ):
            messagebox.showwarning(
                "Kalite yok",
                "Seçilen kalite bu videoda bulunmuyor.",
            )
            return

        if not self.klasor:
            self.klasor = config.get_download_path()
            self._update_path_display()

        self._downloading = True
        self._set_controls_enabled(False)
        self.ui.progress_bar.configure(mode="determinate")
        self.ui.progress_bar.set(0)
        self._show_progress_bar()
        self.ui.status_label.configure(text="İndiriliyor...")

        options = DownloadOptions(
            quality=self.ui.video_quality_var.get(),
            media_type=self.ui.selected_media_type,
            output_path=self.klasor,
        )
        thread = threading.Thread(
            target=self._download_worker, args=(link, options), daemon=True
        )
        thread.start()

    def _download_worker(self, link: str, options: DownloadOptions):
        try:
            self.downloader.download(
                link, options=options, progress_callback=self._on_download_progress
            )
            self.after(0, self._on_download_success)
        except Exception as exc:
            self.after(0, lambda: self._on_download_error(str(exc)))

    def _on_download_progress(self, status: dict):
        state = status.get("status")
        if state == "downloading":
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            done = status.get("downloaded_bytes") or 0
            percent = (done / total) if total else 0
            speed = status.get("speed")
            parts = ["İndiriliyor"]
            if total:
                parts.append(f"{percent * 100:.1f}%")
            if speed:
                parts.append(f"{format_bytes(int(speed), exact=True)}/s")

            def update():
                self.ui.progress_bar.set(min(max(percent, 0), 1.0))
                self.ui.status_label.configure(text=" · ".join(parts))

            self.after(0, update)
        elif state == "finished":
            self.after(0, self._on_download_processing)

    def _on_download_processing(self):
        self.ui.progress_bar.set(1)
        self.ui.status_label.configure(text="İşleniyor...")

    def _on_download_success(self):
        self._downloading = False
        self._hide_progress_bar()
        self.ui.status_label.configure(text="✅ İndirme tamamlandı!")
        self._set_controls_enabled(True)

    def _on_download_error(self, error: str):
        self._downloading = False
        self._hide_progress_bar()
        self.ui.status_label.configure(text="❌ Hata oluştu")
        self._set_controls_enabled(True)
        messagebox.showerror("Hata", error)
