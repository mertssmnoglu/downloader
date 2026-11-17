import os
from yt_dlp import YoutubeDL
from youtube import DownloadOptions, Quality, MediaType, YoutubeDownloader

QUALITY_MAX_HEIGHT = {
    Quality.VIDEO_144P: 144,
    Quality.VIDEO_240P: 240,
    Quality.VIDEO_360P: 360,
    Quality.VIDEO_480P: 480,
    Quality.VIDEO_720P: 720,
    Quality.VIDEO_1080P: 1080,
    Quality.VIDEO_2K: 1440,
    Quality.VIDEO_4K: 2160,
}

EXTRACTOR_ARGS = {
    "youtube": {
        "remote_components": ["ejs:github"],
    }
}

# MP3 export bitrate used by the audio postprocessor.
AUDIO_BITRATE_KBPS = 192


def format_bytes(num_bytes: int | None, exact: bool = True) -> str:
    if not num_bytes:
        return "Bilinmiyor"
    size = float(num_bytes)
    prefix = "" if exact else "~"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{prefix}{int(size)} {unit}"
            return f"{prefix}{size:.1f} {unit}"
        size /= 1024
    return f"{prefix}{size:.1f} TB"


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "Bilinmiyor"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _filesize_of(fmt: dict | None, duration: float | None) -> tuple[int | None, bool]:
    if not fmt:
        return None, False
    if fmt.get("filesize"):
        return int(fmt["filesize"]), True
    if fmt.get("filesize_approx"):
        return int(fmt["filesize_approx"]), False
    bitrate = fmt.get("tbr") or fmt.get("vbr") or fmt.get("abr")
    if bitrate and duration:
        return int(float(bitrate) * 125 * duration), False
    return None, False


def _is_hls(fmt: dict) -> bool:
    protocol = fmt.get("protocol") or ""
    return "m3u8" in protocol


def _is_usable_format(fmt: dict, allow_hls: bool = True) -> bool:
    if not isinstance(fmt, dict):
        return False
    if fmt.get("protocol") in ("mhtml", "mhtml_dash"):
        return False
    if fmt.get("format_note") in ("storyboard", "Premium"):
        return False
    if not allow_hls and _is_hls(fmt):
        return False
    return True


def _max_video_height(formats: list) -> int:
    heights = []
    for fmt in formats:
        if not _is_usable_format(fmt):
            continue
        if fmt.get("vcodec") in (None, "none"):
            continue
        height = fmt.get("height") or 0
        if height:
            heights.append(height)
    return max(heights, default=0)


def _map_height_to_quality(height: int) -> str | None:
    if not height:
        return None
    if height <= 180:
        return Quality.VIDEO_144P
    if height <= 300:
        return Quality.VIDEO_240P
    if height <= 420:
        return Quality.VIDEO_360P
    if height <= 600:
        return Quality.VIDEO_480P
    if height <= 900:
        return Quality.VIDEO_720P
    if height <= 1260:
        return Quality.VIDEO_1080P
    if height <= 1800:
        return Quality.VIDEO_2K
    return Quality.VIDEO_4K


def _available_quality_set(formats: list) -> set[str]:
    found = set()
    for fmt in formats:
        if not _is_usable_format(fmt):
            continue
        if fmt.get("vcodec") in (None, "none"):
            continue
        quality = _map_height_to_quality(fmt.get("height") or 0)
        if quality:
            found.add(quality)
    return found


def _codec_rank(vcodec: str | None) -> int:
    codec = (vcodec or "").lower()
    if codec.startswith("av01") or codec.startswith("av1"):
        return 3
    if codec.startswith("vp9") or codec.startswith("vp09"):
        return 2
    if codec.startswith("avc"):
        return 1
    return 0


def _pick_video_audio(
    formats: list, max_height: int | None
) -> tuple[dict | None, dict | None]:
    picked = _select_streams(formats, max_height, allow_hls=False)
    if picked != (None, None):
        return picked
    return _select_streams(formats, max_height, allow_hls=True)


def _select_streams(
    formats: list, max_height: int | None, allow_hls: bool
) -> tuple[dict | None, dict | None]:
    video_only = []
    audio_only = []
    progressive = []

    for fmt in formats:
        if not _is_usable_format(fmt, allow_hls=allow_hls):
            continue

        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        height = fmt.get("height") or 0
        is_video = vcodec not in (None, "none")
        is_audio = acodec not in (None, "none")

        if is_video and not is_audio:
            if max_height is None or height <= max_height:
                video_only.append(fmt)
        elif is_audio and not is_video:
            audio_only.append(fmt)
        elif is_video and is_audio:
            if max_height is None or height <= max_height:
                progressive.append(fmt)

    def video_score(fmt: dict) -> tuple:
        protocol = fmt.get("protocol") or ""
        is_http = 1 if protocol.startswith("http") and "m3u8" not in protocol else 0
        has_size = 1 if fmt.get("filesize") else 0
        return (
            fmt.get("height") or 0,
            is_http,
            has_size,
            _codec_rank(fmt.get("vcodec")),
            fmt.get("fps") or 0,
            fmt.get("tbr") or fmt.get("vbr") or 0,
        )

    def audio_score(fmt: dict) -> tuple:
        protocol = fmt.get("protocol") or ""
        is_http = 1 if protocol.startswith("http") and "m3u8" not in protocol else 0
        has_size = 1 if fmt.get("filesize") else 0
        return (
            is_http,
            has_size,
            fmt.get("abr") or fmt.get("tbr") or 0,
        )

    best_video = max(video_only, key=video_score, default=None)
    best_audio = max(audio_only, key=audio_score, default=None)
    if best_video and best_audio:
        return best_video, best_audio

    best_progressive = max(progressive, key=video_score, default=None)
    if best_progressive:
        return best_progressive, None

    if best_video:
        return best_video, None
    return None, None


class YtDlpDownloader(YoutubeDownloader):
    def download(self, url: str, options: DownloadOptions, progress_callback=None) -> None:
        yt_dlp_options = self._convert_options(options)
        if progress_callback:
            yt_dlp_options["progress_hooks"] = [progress_callback]
        with YoutubeDL(yt_dlp_options) as ydl:  # type: ignore because of yt-dlp does not export types
            print(f"Starting download: {url}")
            ydl.download([url])
            print("Download complete!")

    def get_video_info(self, url: str) -> dict:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "extractor_args": EXTRACTOR_ARGS,
        }
        with YoutubeDL(ydl_opts) as ydl:  # type: ignore because of yt-dlp does not export types
            info = ydl.extract_info(url, download=False)

        if not info:
            raise ValueError("Video bilgisi alınamadı")
        if info.get("_type") == "playlist":
            entries = [entry for entry in (info.get("entries") or []) if entry]
            if not entries:
                raise ValueError("Video bulunamadı")
            info = entries[0]

        formats = info.get("formats") or []
        duration = info.get("duration")
        max_height = _max_video_height(formats)
        available_qualities = _available_quality_set(formats)
        estimates = {
            MediaType.AUDIO: self._estimate_audio(duration, formats),
        }
        for quality in Quality.VIDEO_CHOICES:
            estimates[quality] = self.estimate_download(
                info,
                quality,
                MediaType.VIDEO,
                max_height=max_height,
                available_qualities=available_qualities,
            )

        return {
            "title": info.get("title") or "Başlıksız",
            "duration": duration,
            "view_count": info.get("view_count"),
            "formats": formats,
            "max_height": max_height,
            "available_qualities": sorted(
                available_qualities,
                key=lambda item: Quality.VIDEO_CHOICES.index(item),
            ),
            "estimates": estimates,
        }

    def estimate_download(
        self,
        info: dict,
        quality: str,
        media_type: str,
        max_height: int | None = None,
        available_qualities: set[str] | None = None,
    ) -> dict:
        formats = info.get("formats") or []
        duration = info.get("duration")

        if media_type == MediaType.AUDIO:
            return self._estimate_audio(duration, formats)

        if max_height is None:
            max_height = _max_video_height(formats)
        if available_qualities is None:
            available_qualities = _available_quality_set(formats)

        quality_height = QUALITY_MAX_HEIGHT.get(quality)
        available = quality in available_qualities
        video, audio = _pick_video_audio(formats, quality_height)

        total = 0
        exact = True
        found = False
        for fmt in (video, audio):
            size, is_exact = _filesize_of(fmt, duration)
            if size:
                total += size
                found = True
                exact = exact and is_exact
            elif fmt is not None:
                exact = False

        source = video or {}
        height = source.get("height")
        width = source.get("width")
        if width and height:
            resolution = f"{width}x{height}"
        elif height:
            resolution = f"{height}p"
        else:
            resolution = None

        return {
            "bytes": total if found else None,
            "exact": exact if found else False,
            "height": height,
            "resolution": resolution,
            "available": available,
        }

    def _estimate_audio(self, duration: float | None, formats: list) -> dict:
        if duration:
            return {
                "bytes": int(AUDIO_BITRATE_KBPS * 125 * duration),
                "exact": False,
                "height": None,
                "resolution": f"MP3 {AUDIO_BITRATE_KBPS} kbps",
                "available": True,
            }

        audio_only = [
            fmt
            for fmt in formats
            if _is_usable_format(fmt)
            and fmt.get("acodec") not in (None, "none")
            and fmt.get("vcodec") in (None, "none")
        ]
        best_audio = max(
            audio_only,
            key=lambda fmt: fmt.get("abr") or fmt.get("tbr") or 0,
            default=None,
        )
        size, exact = _filesize_of(best_audio, duration)
        return {
            "bytes": size,
            "exact": exact,
            "height": None,
            "resolution": "MP3",
            "available": True,
        }

    def _convert_options(self, options: DownloadOptions) -> dict:  # type: ignore
        if options.media_type == MediaType.AUDIO:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(options.output_path, "%(title)s.%(ext)s"),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": str(AUDIO_BITRATE_KBPS),
                    }
                ],
                "quiet": True,
                "noplaylist": True,
            }
        else:
            format_selector = self._video_format_selector(options.quality)
            ydl_opts = {
                "format": format_selector,
                "outtmpl": os.path.join(options.output_path, "%(title)s.%(ext)s"),
                "extractor_args": EXTRACTOR_ARGS,
                "merge_output_format": "mp4",
                "quiet": False,
                "no_warnings": False,
                "noplaylist": True,
            }
        return ydl_opts

    @staticmethod
    def _video_format_selector(quality: str) -> str:
        max_height = QUALITY_MAX_HEIGHT.get(quality)
        if max_height is None:
            return "bv*[protocol^=http]+ba[protocol^=http]/bv*+ba/b"
        return (
            f"bv*[height<={max_height}][protocol^=http]+ba[protocol^=http]/"
            f"bv*[height<={max_height}]+ba/"
            f"b[height<={max_height}]"
        )
