from __future__ import annotations

import re
from typing import Any, Dict, Optional

import yt_dlp

from utils.media_url import normalize_single_media_url
from PyQt6.QtCore import QThread, pyqtSignal


class LinkCheckWorker(QThread):
    checked = pyqtSignal(bool, dict)
    status = pyqtSignal(str)

    def __init__(self, url: str, cookies_path: Optional[str] = None) -> None:
        super().__init__()
        self.url = normalize_single_media_url(url.strip())
        self.cookies_path = cookies_path.strip() if cookies_path else None

    def _build_options(self) -> Dict[str, Any]:
        ydl_opts: Dict[str, Any] = {
            "quiet": True,
            "ignoreerrors": True,
            "skip_download": True,
            "format": "bestvideo+bestaudio/best",
            "noplaylist": True,
        }

        if self.cookies_path:
            ydl_opts["cookiefile"] = self.cookies_path

        return ydl_opts

    def run(self) -> None:
        try:
            self.status.emit("Проверка ссылки...")

            if not re.match(r"^https?://", self.url):
                self.status.emit("Некорректный URL")
                self.checked.emit(False, {})
                return

            with yt_dlp.YoutubeDL(self._build_options()) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    self.status.emit("Не удалось получить информацию о медиа")
                    self.checked.emit(False, {})
                    return

                info_dict: Dict[str, Any] = dict(info)

                formats = info_dict.get("formats", []) or []
                video_formats = [
                    {
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "resolution": f"{f.get('width', '?')}x{f.get('height', '?')}",
                        "fps": f.get("fps"),
                        "tbr": f.get("tbr"),
                        "height": f.get("height"),
                    }
                    for f in formats
                    if f.get("vcodec") != "none"
                ]
                audio_formats = [
                    {
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "abr": f.get("abr"),
                    }
                    for f in formats
                    if f.get("acodec") != "none" and f.get("vcodec") == "none"
                ]

                info_dict["video_formats"] = video_formats
                info_dict["audio_formats"] = audio_formats

                self.status.emit("Ссылка корректна, метаданные получены")
                self.checked.emit(True, info_dict)

        except Exception as exc:
            self.status.emit(f"Ошибка проверки: {exc}")
            self.checked.emit(False, {})
