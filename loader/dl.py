from __future__ import annotations

import glob
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from io import BytesIO
from typing import Any, Dict, Optional, List, cast
from .hw_detect import get_hwaccels_all
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC, COMM, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, TPOS, TXXX
from mutagen.mp3 import MP3
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from ui.guilogger import GuiLogger

from utils.media_url import normalize_single_media_url

try:
    import yt_dlp
except ImportError as exc:
    raise RuntimeError(
        "yt-dlp not found."
    ) from exc

def _run_with_retry(fn, attempts=4, base_delay=0.8, exceptions=(Exception)):
    last_exc = None

    for i in range(attempts):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if i < attempts - 1:
                time.sleep(base_delay * (2 ** i))

    if last_exc is not None:
        raise last_exc

    raise RuntimeError("Retry failed without captured exception")

YDLParams = Dict[str, Any]

def _which_any(names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None

def _resolve_ffmpeg_bin(provided: Optional[str]) -> Optional[str]:
    if provided:
        candidate = provided.strip()
        if candidate and os.path.exists(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    return _which_any(("ffmpeg", "ffmpeg.exe"))


def _resolve_ffprobe_bin(provided: Optional[str], ffmpeg_bin: Optional[str]) -> Optional[str]:
    if provided:
        candidate = provided.strip()
        if candidate and os.path.exists(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    if ffmpeg_bin:
        base, ext = os.path.splitext(ffmpeg_bin)
        sibling = f"{base.replace('ffmpeg', 'ffprobe')}{ext}"
        if os.path.exists(sibling):
            return sibling

    return _which_any(("ffprobe", "ffprobe.exe"))


def _normalize_text_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    if isinstance(value, (list, tuple, set)):
        parts = [part for part in (_normalize_text_value(item) for item in value) if part]
        return ", ".join(parts) if parts else None
    text = str(value).strip()
    return text or None


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        text = _normalize_text_value(value)
        if text:
            return text
    return None


def _safe_int_text(value: Any) -> Optional[str]:
    text = _normalize_text_value(value)
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or None


def _image_bytes_to_jpeg_bytes(data: bytes) -> tuple[bytes, str]:
    with Image.open(BytesIO(data)) as image:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=95, optimize=True)
        return buffer.getvalue(), "image/jpeg"


def _read_image_bytes_from_source(source: str) -> Optional[tuple[bytes, str]]:
    try:
        if source.startswith(("http://", "https://")):
            with urllib.request.urlopen(source, timeout=10) as response:
                data = response.read()
        elif os.path.exists(source):
            with open(source, "rb") as file_obj:
                data = file_obj.read()
        else:
            return None

        try:
            return _image_bytes_to_jpeg_bytes(data)
        except Exception:
            lowered = source.lower()
            if lowered.endswith(".png"):
                return data, "image/png"
            if lowered.endswith(".webp"):
                return data, "image/webp"
            if lowered.endswith((".jpg", ".jpeg")):
                return data, "image/jpeg"
            return data, "image/jpeg"
    except Exception:
        return None


class DownloadCancelled(RuntimeError):
    pass


class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        url: str,
        mode: str,
        base_dir: str,
        selected_format: Optional[str] = None,
        ffmpeg_path: Optional[str] = None,
        cookies_path: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.url = normalize_single_media_url(url.strip())
        self.mode = mode
        self.base_dir = base_dir
        self.selected_format = selected_format
        self.ffmpeg_path = ffmpeg_path.strip() if ffmpeg_path else None
        self.cookies_path = cookies_path.strip() if cookies_path else None
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._active_process: Optional[subprocess.Popen[str]] = None
        self._hwaccels: Optional[List[str]] = None
        self._cached_encoder: Optional[str] = None

    def _raise_if_cancelled(self) -> None:
        if self.isInterruptionRequested():
            self._cancel_running_process()
            raise DownloadCancelled("Download cancelled by user")

    def _cancel_running_process(self) -> None:
        proc = self._active_process
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
        self._active_process = None

    def _patch_subprocess_tracking(self):
        original_popen = subprocess.Popen

        def tracked_popen(*popen_args, **popen_kwargs):
            proc = original_popen(*popen_args, **popen_kwargs)
            self._active_process = proc
            return proc

        subprocess.Popen = tracked_popen  # type: ignore[assignment]
        return original_popen

    def cancel(self) -> None:
        self.requestInterruption()
        self._pause_event.set()
        self._cancel_running_process()


    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    def is_paused(self) -> bool:
        return not self._pause_event.is_set()

    def _wait_if_paused(self) -> None:
        while not self._pause_event.is_set():
            self._raise_if_cancelled()
            time.sleep(0.1)

    def hook(self, d: Dict[str, Any]) -> None:
        self._raise_if_cancelled()
        self._wait_if_paused()

        status = d.get("status")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)

            if isinstance(total, (int, float)) and total > 0:
                percent = int(min(100, max(0, downloaded / total * 100)))
                self.progress.emit(percent)

        elif status == "finished":
            self.progress.emit(100)
            self.status.emit("File downloaded")

    def _run_ffmpeg(self, args: list[str]) -> tuple[bool, str]:
        ffmpeg_bin = _resolve_ffmpeg_bin(self.ffmpeg_path) or "ffmpeg"
        cmd = [ffmpeg_bin, "-y", *args]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._active_process = proc

            while True:
                self._raise_if_cancelled()
                self._wait_if_paused()
                try:
                    stdout, stderr = proc.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue

            if proc.returncode != 0:
                err = (stderr or stdout or "").strip()
                return False, err
            return True, ""
        except DownloadCancelled:
            raise
        except Exception as exc:
            return False, str(exc)
        finally:
            self._active_process = None

    def _detect_hw_encoder(self) -> str:
        if self._cached_encoder is not None:
            return self._cached_encoder

        ok, out = self._run_ffmpeg(["-hide_banner", "-encoders"])
        if not ok:
            self._cached_encoder = "libx264"
            return self._cached_encoder

        lowered = out.lower()
        if "h264_nvenc" in lowered:
            self._cached_encoder = "h264_nvenc"
        elif "h264_qsv" in lowered:
            self._cached_encoder = "h264_qsv"
        elif "h264_amf" in lowered:
            self._cached_encoder = "h264_amf"
        else:
            self._cached_encoder = "libx264"

        return self._cached_encoder
    

    def _video_encoder_args(self, encoder: str) -> list[str]:
        if encoder == "libx264":
            return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        return ["-c:v", encoder, "-preset", "p1", "-cq", "23"]

    def _get_final_path(
        self,
        ydl: yt_dlp.YoutubeDL,
        result: Dict[str, Any],
    ) -> Optional[str]:
        filepath = result.get("filepath")
        if isinstance(filepath, str) and os.path.isfile(filepath):
            return filepath

        requested = result.get("requested_downloads")
        if isinstance(requested, list):
            for entry in requested:
                if isinstance(entry, dict):
                    path = entry.get("filepath")
                    if isinstance(path, str) and os.path.isfile(path):
                        return path

        try:
            prepared = ydl.prepare_filename(cast(Any, result))
            if isinstance(prepared, str) and os.path.exists(prepared):
                return prepared
        except Exception:
            pass

        return None

    def _has_audio_stream(self, path: str) -> bool:
        ffmpeg_bin = _resolve_ffprobe_bin(None, _resolve_ffmpeg_bin(self.ffmpeg_path))
        if not ffmpeg_bin:
            return False

        try:
            proc = subprocess.run(
                [
                    ffmpeg_bin,
                    "-v",
                    "error",
                    "-select_streams",
                    "a",
                    "-show_entries",
                    "stream=index",
                    "-of",
                    "csv=p=0",
                    path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            return bool(proc.stdout.strip())
        except Exception:
            return False

    def _find_generated_special_file(self, base_stem: str, mode: str) -> Optional[str]:
        if mode == "metadata":
            candidate = f"{base_stem}.info.json"
            return candidate if os.path.isfile(candidate) else None

        if mode != "thumbnail":
            return None

        image_exts = {"jpg", "jpeg", "png", "webp", "avif", "gif", "bmp", "tif", "tiff"}
        candidates: list[str] = []

        for path in glob.glob(f"{base_stem}.*"):
            if path.endswith(".info.json"):
                continue
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if ext in image_exts:
                candidates.append(path)

        if not candidates:
            return None

        candidates.sort(key=lambda item: os.path.getmtime(item), reverse=True)
        return candidates[0]

    def _download_audio_only(self) -> Optional[str]:
        self._raise_if_cancelled()
        self._wait_if_paused()
        self.status.emit("Downloading audio...")

        outtmpl = os.path.join(self.base_dir, "%(title).200s_%(id)s.audio.%(ext)s")

        ydl_opts: YDLParams = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": False,
            "no_warnings": True,
            "ignoreerrors": False,
            "progress_hooks": [self.hook],
        }

        if self.cookies_path and os.path.isfile(self.cookies_path):
            ydl_opts["cookiefile"] = self.cookies_path

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                result = cast(Optional[Dict[str, Any]], _run_with_retry(lambda: _run_with_retry(lambda: ydl.extract_info(self.url, download=True))))
                if not result:
                    return None
                return self._get_final_path(ydl, result)
        except DownloadCancelled:
            raise
        except Exception:
            return None

    def _select_hwaccel(self, encoder: str) -> Optional[str]:
        available = set(get_hwaccels_all(self.ffmpeg_path or "ffmpeg"))

        gpu_priority = ["cuda", "qsv", "d3d11va", "dxva2", "d3d12va", "vaapi"]

        encoder_map = {
            "h264_nvenc": ["cuda", "qsv", "d3d11va", "dxva2", "vaapi"],
            "h264_qsv": ["qsv", "d3d11va", "dxva2", "cuda", "vaapi"],
            "h264_amf": ["d3d11va", "dxva2", "vaapi", "qsv", "cuda"],
        }

        preferred = encoder_map.get(encoder, gpu_priority)

        for hw in preferred:
            if hw in available:
                return hw

        for hw in gpu_priority:
            if hw in available:
                return hw

        return None


    def _merge_video_audio(self, video_path: str, audio_path: str) -> Optional[str]:
        root, _ = os.path.splitext(video_path)
        output_path = f"{root}.merged.mp4"

        self._wait_if_paused()
        encoder = self._detect_hw_encoder()
        self.status.emit("Merging video and audio...")

        hwaccel = self._select_hwaccel(encoder)

        def build_args(use_hw: bool) -> List[str]:
            args: List[str] = []

            if use_hw and hwaccel:
                args += ["-hwaccel", hwaccel]

            args += [
                "-fflags", "+genpts",
                "-i", video_path,
                "-i", audio_path,
                "-map", "0:v:0",
                "-map", "1:a:0",
            ]

            args += self._video_encoder_args(encoder)

            args += [
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-movflags", "+faststart",
                output_path,
            ]

            return args

        ok, err = self._run_ffmpeg(build_args(True))

        if not ok and encoder != "libx264":
            ok, err = self._run_ffmpeg(build_args(False))

            if not ok:
                ok, err = self._run_ffmpeg([
                    "-fflags", "+genpts",
                    "-i", video_path,
                    "-i", audio_path,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    *self._video_encoder_args("libx264"),
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-movflags", "+faststart",
                    output_path,
                ])

        if not ok:
            self.status.emit(f"Merge error: {err}")
            return None

        return output_path


    def _normalize_video(self, source_path: str) -> Optional[str]:
        root, _ = os.path.splitext(source_path)
        output_path = f"{root}.fix.mp4"

        self._wait_if_paused()
        encoder = self._detect_hw_encoder()
        self.status.emit(f"HW encode ({encoder})..." if encoder != "libx264" else "Re-encode (libx264)...")

        hwaccel = self._select_hwaccel(encoder)

        def build_args(use_hw: bool) -> List[str]:
            args: List[str] = []

            if use_hw and hwaccel:
                args += ["-hwaccel", hwaccel]

            args += [
                "-fflags", "+genpts",
                "-i", source_path,
            ]

            args += self._video_encoder_args(encoder)

            args += [
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-movflags", "+faststart",
                output_path,
            ]

            return args

        ok, err = self._run_ffmpeg(build_args(True))

        if not ok and encoder != "libx264":
            ok, err = self._run_ffmpeg(build_args(False))

            if not ok:
                ok, err = self._run_ffmpeg(build_args(False))

        if not ok:
            self.status.emit(f"Error: {err}")
            return None

        return output_path

        root, _ = os.path.splitext(source_path)
        output_path = f"{root}.syncfix.mp4"

        self._wait_if_paused()
        encoder = self._detect_hw_encoder()
        self.status.emit(f"HW encode ({encoder})..." if encoder != "libx264" else "Re-encode (libx264)...")

        hwaccel = self._select_hwaccel(encoder)

        args: List[str] = []
        if hwaccel:
            args.extend(["-hwaccel", hwaccel])
            if hwaccel in ("cuda", "qsv", "vaapi"):
                args.extend(["-hwaccel_output_format", hwaccel])

        args.extend([
            "-fflags", "+genpts",
            "-i", source_path,
            *self._video_encoder_args(encoder),
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ])

        ok, err = self._run_ffmpeg(args)
        if not ok and encoder != "libx264":
            fallback_args: List[str] = []
            if hwaccel:
                fallback_args.extend(["-hwaccel", hwaccel])
            fallback_args.extend([
                "-fflags", "+genpts",
                "-i", source_path,
                *self._video_encoder_args("libx264"),
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-movflags", "+faststart",
                output_path,
            ])
            ok, err = self._run_ffmpeg(fallback_args)

        if not ok:
            self.status.emit(f"Error: {err}")
            return None

        return output_path

    def _audio_metadata_parsers(self) -> list[str]:
        return [
            "%(uploader|channel|creator|artist|)s:%(artist)s",
            "%(uploader|channel|creator|artist|)s:%(album_artist)s",
            "%(playlist_title|album|)s:%(album)s",
            "%(title|)s:%(track)s",
            "%(upload_date>%Y|)s:%(year)s",
            "%(webpage_url|)s:%(comment)s",
        ]

    def _find_thumbnail_source(self, base_stem: str, info: Dict[str, Any]) -> Optional[str]:
        image_exts = {"jpg", "jpeg", "png", "webp", "avif", "gif", "bmp", "tif", "tiff"}
        candidates: list[str] = []

        for path in glob.glob(f"{base_stem}.*"):
            if path.endswith(".info.json"):
                continue
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            if ext in image_exts:
                candidates.append(path)

        if candidates:
            candidates.sort(key=lambda item: os.path.getmtime(item), reverse=True)
            return candidates[0]

        thumbnail = info.get("thumbnail")
        if isinstance(thumbnail, str) and thumbnail.strip():
            return thumbnail.strip()

        thumbnails = info.get("thumbnails")
        if isinstance(thumbnails, list):
            best_url = None
            best_score = -1
            for item in thumbnails:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not isinstance(url, str) or not url.strip():
                    continue

                width = item.get("width")
                height = item.get("height")
                score = 0
                if isinstance(width, int) and isinstance(height, int):
                    score = width * height
                elif isinstance(height, int):
                    score = height

                if score >= best_score:
                    best_score = score
                    best_url = url.strip()

            if best_url:
                return best_url

        return None

    def _collect_audio_tag_values(self, info: Dict[str, Any]) -> Dict[str, Optional[str]]:
        title = _first_text(info.get("track"), info.get("title"))
        artist = _first_text(info.get("artist"), info.get("creator"), info.get("uploader"), info.get("channel"))
        album_artist = _first_text(info.get("album_artist"), artist)
        album = _first_text(info.get("album"), info.get("playlist_title"))
        track_number = _first_text(info.get("track_number"), info.get("track_no"), info.get("playlist_index"))
        disc_number = _first_text(info.get("disc_number"), info.get("disc_no"))
        genre = _first_text(info.get("genre"))
        year = _safe_int_text(info.get("release_year") or info.get("year"))
        if year is None:
            upload_date = _safe_int_text(info.get("upload_date"))
            if upload_date and len(upload_date) >= 4:
                year = upload_date[:4]
        date_text = _safe_int_text(info.get("upload_date"))
        comment = _first_text(info.get("description"))
        webpage_url = _first_text(info.get("webpage_url"), info.get("original_url"))
        extractor = _first_text(info.get("extractor"))
        return {
            "title": title,
            "artist": artist,
            "album_artist": album_artist,
            "album": album,
            "track_number": track_number,
            "disc_number": disc_number,
            "genre": genre,
            "year": year,
            "date_text": date_text,
            "comment": comment,
            "webpage_url": webpage_url,
            "extractor": extractor,
        }

    def _write_mp3_tags(self, path: str, info: Dict[str, Any]) -> None:
        audio = MP3(path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        tags = audio.tags
        if tags is None:
            return

        values = self._collect_audio_tag_values(info)

        def set_text(frame_id: str, frame_cls: Any, value: Optional[str]) -> None:
            if not value:
                return
            try:
                tags.delall(frame_id)
            except Exception:
                pass
            tags.add(frame_cls(encoding=3, text=value))

        set_text("TIT2", TIT2, values["title"])
        set_text("TPE1", TPE1, values["artist"])
        set_text("TPE2", TPE2, values["album_artist"])
        set_text("TALB", TALB, values["album"])
        set_text("TRCK", TRCK, values["track_number"])
        set_text("TPOS", TPOS, values["disc_number"])
        set_text("TCON", TCON, values["genre"])

        if values["year"]:
            try:
                tags.delall("TDRC")
            except Exception:
                pass
            tags.add(TDRC(encoding=3, text=values["year"]))

        if values["comment"]:
            try:
                tags.delall("COMM")
            except Exception:
                pass
            tags.add(COMM(encoding=3, lang="eng", desc="Comment", text=values["comment"]))

        for key in ("webpage_url", "extractor", "date_text"):
            value = values.get(key)
            if not value:
                continue
            try:
                tags.add(TXXX(encoding=3, desc=key, text=value))
            except Exception:
                pass

        cover_temp_path = None

        thumbnail_source = self._find_thumbnail_source(os.path.splitext(path)[0], info)
        if thumbnail_source:
            image_data = _read_image_bytes_from_source(thumbnail_source)
            if image_data:
                data, mime_type = image_data

                try:
                    tags.delall("APIC")
                except Exception:
                    pass

                tags.add(
                    APIC(
                        encoding=3,
                        mime=mime_type,
                        type=3,
                        desc="Cover",
                        data=data,
                    )
                )

                if os.path.isfile(thumbnail_source):
                    cover_temp_path = thumbnail_source

        audio.save(v2_version=3)

        if cover_temp_path:
            try:
                os.remove(cover_temp_path)
            except Exception:
                pass

    def _build_ydl_opts(self) -> YDLParams:
        self._wait_if_paused()
        ffmpeg_bin = _resolve_ffmpeg_bin(self.ffmpeg_path)

        ydl_opts: YDLParams = {
            "ffmpeg_location": ffmpeg_bin,
            "noplaylist": True,
            "progress_hooks": [self.hook],
            "quiet": False,
            "no_warnings": True,
            "ignoreerrors": False,
            "logger": GuiLogger(self.status.emit),
            "windowsfilenames": True,
            "outtmpl": os.path.join(self.base_dir, "%(title).200s_%(id)s.%(ext)s"),
            "retries": 10,
            "fragment_retries": 10,
            "socket_timeout": 15,
            "concurrent_fragment_downloads": min(16, max(4, (os.cpu_count() or 4))),
        }

        if self.cookies_path and os.path.isfile(self.cookies_path):
            ydl_opts["cookiefile"] = self.cookies_path

        aria2c = shutil.which("aria2c")
        if aria2c:
            ydl_opts["external_downloader"] = aria2c
            ydl_opts["external_downloader_args"] = ["-x", "16", "-s", "16", "-k", "1M"]

        if self.mode == "video":
            ydl_opts["merge_output_format"] = "mkv"
            ydl_opts["format"] = self.selected_format or "bv*+ba/b"
        elif self.mode == "audio":
            ydl_opts.update(
                {
                    "format": "bestaudio/best",
                    "writethumbnail": True,
                    "parse_metadata": self._audio_metadata_parsers(),
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        },
                    ],
                }
            )
        elif self.mode == "thumbnail":
            ydl_opts["skip_download"] = True
            ydl_opts["writethumbnail"] = True
        elif self.mode == "metadata":
            ydl_opts["skip_download"] = True
            ydl_opts["writeinfojson"] = True

        return ydl_opts

    def run(self) -> None:
        original_popen = self._patch_subprocess_tracking()
        try:
            self._raise_if_cancelled()
            self._wait_if_paused()
            os.makedirs(self.base_dir, exist_ok=True)

            ydl_opts = self._build_ydl_opts()

            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                result: Optional[Dict[str, Any]]

                try:
                    self._wait_if_paused()
                    result = cast(Optional[Dict[str, Any]], _run_with_retry(lambda: ydl.extract_info(self.url, download=True)))
                except DownloadCancelled:
                    raise
                except Exception as exc:
                    self.status.emit(f"Warning: {exc}")
                    result = None

                if not result:
                    self.status.emit("Error: не удалось получить данные о файле")
                    return

                final_path = self._get_final_path(ydl, result)

                if self.mode in {"thumbnail", "metadata"}:
                    prepared = None
                    try:
                        prepared = ydl.prepare_filename(cast(Any, result))
                    except Exception:
                        prepared = None

                    special_path = None
                    if isinstance(prepared, str) and prepared:
                        special_path = self._find_generated_special_file(os.path.splitext(prepared)[0], self.mode)

                    if special_path:
                        self.status.emit(f"Done: {special_path}")
                    else:
                        self.status.emit("Ready")

                    self.status.emit("Download completed successfully")
                    return

                if not final_path:
                    self.status.emit("Error: не удалось определить путь файла")
                    return

                if self.mode == "video":
                    self._wait_if_paused()
                    if not self._has_audio_stream(final_path):
                        self.progress.emit(0)
                        audio_path = self._download_audio_only()
                        if audio_path:
                            merged = self._merge_video_audio(final_path, audio_path)
                            if merged:
                                try:
                                    os.remove(final_path)
                                    os.remove(audio_path)
                                except Exception:
                                    pass
                                final_path = merged

                    repaired_path = self._normalize_video(final_path)

                    if repaired_path:
                        if repaired_path != final_path and os.path.exists(final_path):
                            try:
                                os.remove(final_path)
                            except Exception:
                                pass

                        final_path = repaired_path
                        self.status.emit(f"Done: {final_path}")
                    else:
                        self.status.emit(f"File downloaded, but post-processing failed: {final_path}")
                else:
                    if self.mode == "audio":
                        try:
                            self._write_mp3_tags(final_path, result)
                        except DownloadCancelled:
                            raise
                        except Exception as exc:
                            self.status.emit(f"Warning: не удалось записать теги: {exc}")
                    self.status.emit(f"Done: {final_path}")

            self.status.emit("Download completed successfully")

        except DownloadCancelled as exc:
            self.status.emit(str(exc))
        except Exception as exc:
            self.status.emit(f"Error: {exc}")

        finally:
            subprocess.Popen = original_popen  # type: ignore[assignment]
            self._cancel_running_process()
            self._pause_event.set()
            self.finished.emit()
