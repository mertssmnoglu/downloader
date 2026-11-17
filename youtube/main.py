import abc
from dataclasses import dataclass


class Quality:
    VIDEO_144P = "144p"
    VIDEO_240P = "240p"
    VIDEO_360P = "360p"
    VIDEO_480P = "480p"
    VIDEO_720P = "720p"
    VIDEO_1080P = "1080p"
    VIDEO_2K = "2K"
    VIDEO_4K = "4K"
    VIDEO_BEST = "En kaliteli"

    # Left-to-right on the main screen: largest to smallest.
    VIDEO_CHOICES = [
        VIDEO_4K,
        VIDEO_2K,
        VIDEO_1080P,
        VIDEO_720P,
        VIDEO_480P,
        VIDEO_360P,
        VIDEO_240P,
        VIDEO_144P,
    ]
    HIGH_ROW = [VIDEO_4K, VIDEO_2K, VIDEO_1080P, VIDEO_720P]
    LOW_ROW = [VIDEO_480P, VIDEO_360P, VIDEO_240P, VIDEO_144P]

    # Backward-compatible aliases for existing callers.
    LOW = VIDEO_720P
    HIGH = VIDEO_1080P
    BEST = VIDEO_BEST


class MediaType:
    AUDIO = "audio"
    VIDEO = "video"


@dataclass
class DownloadOptions:
    quality: str = Quality.VIDEO_BEST
    media_type: str = MediaType.AUDIO
    output_path: str = "./"


class YoutubeDownloader(abc.ABC):
    @abc.abstractmethod
    def download(self, url: str, options: DownloadOptions) -> None:
        """Downloads a video from the given URL to the specified path."""
        pass

    @abc.abstractmethod
    def get_video_info(self, url: str) -> dict:
        """Returns metadata about the video (title, duration, etc.)."""
        pass
