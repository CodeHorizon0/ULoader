from __future__ import annotations

import os
import urllib.request
from html import escape
from typing import Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from handlers.on_action import on_download_finished, on_link_checked, on_url_changed
from loader.dl import DownloadWorker
from utils.filters import clean_ansi
from utils.uricheck import LinkCheckWorker

from .styles import LAYOUT, QSS


class AutoResizeLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # type: ignore[override]
        super().setText(text)
        self.adjustSize()

        hint_width = self.sizeHint().width()
        if hint_width > 0:
            self.setFixedWidth(hint_width)


class DownloaderUI(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setMinimumSize(680, 520)

        self.current_info: Optional[dict[str, Any]] = None
        self.worker: Optional[DownloadWorker] = None
        self.link_checker: Optional[LinkCheckWorker] = None
        self._download_cancelled = False
        self._thumbnail_original: Optional[QPixmap] = None

        self.setStyleSheet(QSS)

        self._build_ui()
        self._connect_signals()
        self._setup_timer()
        self._set_idle_state()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout()
        main_layout.setSpacing(LAYOUT["spacing"])
        main_layout.setContentsMargins(*LAYOUT["margins"])

        url_layout = QHBoxLayout()
        url_layout.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("inputField")
        self.url_input.setPlaceholderText("Paste video or audio URL")

        self.check_label = AutoResizeLabel("Ready")
        self.check_label.setObjectName("checkLabel")

        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.check_label, 0)

        main_layout.addLayout(url_layout)

        settings_title = QLabel("Settings")
        settings_title.setObjectName("sectionTitle")

        self.ffmpeg_input = QLineEdit()
        self.ffmpeg_input.setObjectName("inputField")
        self.ffmpeg_input.setPlaceholderText("FFmpeg path (optional)")

        self.cookies_input = QLineEdit()
        self.cookies_input.setObjectName("inputField")
        self.cookies_input.setPlaceholderText("cookies.txt for site access")

        self.type_select = QComboBox()
        self.type_select.setObjectName("selectField")
        self.type_select.addItems(["video", "audio", "thumbnail", "metadata"])

        main_layout.addWidget(settings_title)
        main_layout.addWidget(self.ffmpeg_input)
        main_layout.addWidget(self.cookies_input)
        main_layout.addWidget(self.type_select)

        self.format_label = QLabel("Quality")
        self.format_label.setObjectName("sectionTitle")

        self.format_select = QComboBox()
        self.format_select.setObjectName("selectField")

        self.format_label.hide()
        self.format_select.hide()

        main_layout.addWidget(self.format_label)
        main_layout.addWidget(self.format_select)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(4)
        buttons_row.setContentsMargins(0, 0, 0, 0)

        self.download_button = QPushButton("Download")
        self.download_button.setObjectName("downloadButton")
        self.download_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.download_button.setMaximumHeight(28)
        self.download_button.setMinimumHeight(26)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("pauseButton")
        self.pause_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pause_button.setMaximumHeight(28)
        self.pause_button.setMinimumHeight(26)
        self.pause_button.setEnabled(False)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cancel_button.setMaximumHeight(28)
        self.cancel_button.setMinimumHeight(26)
        self.cancel_button.setEnabled(False)

        buttons_row.addWidget(self.download_button, 1)
        buttons_row.addWidget(self.pause_button, 1)
        buttons_row.addWidget(self.cancel_button, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        main_layout.addLayout(buttons_row)
        main_layout.addSpacing(2)
        main_layout.addWidget(self.progress_bar)

        output_title = QLabel("Logs")
        output_title.setObjectName("sectionTitle")

        self.status_log = QTextEdit()
        self.status_log.setObjectName("statusLog")
        self.status_log.setReadOnly(True)

        self.meta_card = QFrame()
        self.meta_card.setObjectName("metaCard")
        meta_card_layout = QHBoxLayout(self.meta_card)
        meta_card_layout.setContentsMargins(6, 6, 6, 6)
        meta_card_layout.setSpacing(12)

        preview_column = QVBoxLayout()
        preview_column.setSpacing(8)

        self.preview_title = QLabel("Preview")
        self.preview_title.setObjectName("subsectionTitle")

        self.thumbnail_label = QLabel("No preview")
        self.thumbnail_label.setObjectName("thumbnailLabel")
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setFixedSize(128, 72)
        self.thumbnail_label.setWordWrap(True)

        preview_column.addWidget(self.preview_title)
        preview_column.addWidget(self.thumbnail_label, 0, Qt.AlignmentFlag.AlignLeft)
        preview_column.addStretch(1)

        meta_text_column = QVBoxLayout()
        meta_text_column.setSpacing(8)

        self.meta_title = QLabel("Metadata")
        self.meta_title.setObjectName("subsectionTitle")

        self.meta_preview = QTextEdit()
        self.meta_preview.setObjectName("metaPreview")
        self.meta_preview.setReadOnly(True)
        self.meta_preview.setMinimumHeight(90)
        self.meta_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        meta_text_column.addWidget(self.meta_title)
        meta_text_column.addWidget(self.meta_preview, 1)

        meta_card_layout.addLayout(preview_column, 0)
        meta_card_layout.addLayout(meta_text_column, 1)

        main_layout.addWidget(output_title)
        main_layout.addWidget(self.status_log, 1)
        main_layout.addWidget(self.meta_card)

        self.setLayout(main_layout)

    def _connect_signals(self) -> None:
        self.url_input.textChanged.connect(self._handle_url_changed)
        self.type_select.currentTextChanged.connect(self.update_format_options)
        self.download_button.clicked.connect(self.start_download)
        self.pause_button.clicked.connect(self.toggle_pause_download)
        self.cancel_button.clicked.connect(self.cancel_download)

    def _setup_timer(self) -> None:
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.perform_link_check)

    def _set_idle_state(self) -> None:
        self.download_button.setEnabled(True)
        self.download_button.setText("Download")
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.cancel_button.setEnabled(False)
        self.ffmpeg_input.setEnabled(True)
        self.cookies_input.setEnabled(True)
        self.url_input.setEnabled(True)
        self.type_select.setEnabled(True)
        self.format_select.setEnabled(True)
        self.progress_bar.setValue(0)

    def _set_busy_state(self, busy: bool) -> None:
        self.download_button.setEnabled(not busy)
        self.pause_button.setEnabled(busy)
        self.cancel_button.setEnabled(busy)
        self.ffmpeg_input.setEnabled(not busy)
        self.cookies_input.setEnabled(not busy)
        self.url_input.setEnabled(not busy)
        self.type_select.setEnabled(not busy)
        self.format_select.setEnabled(not busy)

    def _set_pause_button_state(self, paused: bool) -> None:
        self.pause_button.setText("Resume" if paused else "Pause")

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        self._stop_link_checker()
        self._stop_download_worker()
        if a0 is not None:
            a0.accept()

    def _stop_link_checker(self) -> None:
        if self.link_checker and self.link_checker.isRunning():
            self.link_checker.requestInterruption()
            self.link_checker.wait(1000)
            if self.link_checker.isRunning():
                self.link_checker.terminate()
                self.link_checker.wait(250)

        self.link_checker = None

    def _stop_download_worker(self) -> None:
        if self.worker and self.worker.isRunning():
            try:
                self.worker.cancel()
            except Exception:
                try:
                    self.worker.resume()
                except Exception:
                    pass
                self.worker.requestInterruption()
            self.worker.wait(2000)
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(250)

        self.worker = None

    def log(self, text: str) -> None:
        self.status_log.append(clean_ansi(text))

    def _handle_url_changed(self, text: str) -> None:
        self.current_info = None
        on_url_changed(self, text)

    def _handle_link_checked(self, valid: bool, info: dict[str, Any]) -> None:
        on_link_checked(self, valid, info)

    def _handle_download_finished(self) -> None:
        cancelled = self._download_cancelled
        self.worker = None
        self._download_cancelled = False
        self._set_idle_state()

        if cancelled:
            self.log("Download cancelled")
        else:
            on_download_finished(self)

    def _sync_meta_preview_height(self) -> None:
        document = self.meta_preview.document()
        if document is None:
            return
        target = int(document.size().height()) + 18
        target = max(90, min(target, 260))
        self.meta_preview.setFixedHeight(target)

    def _schedule_window_resize(self) -> None:
        QTimer.singleShot(0, self._resize_window_to_contents)

    def _resize_window_to_contents(self) -> None:
        self.adjustSize()
        self.updateGeometry()
        hint = self.sizeHint()
        if hint.isValid():
            self.resize(max(760, hint.width()), max(640, hint.height()))

    def clear_metadata_panel(self) -> None:
        self.meta_preview.clear()
        self.meta_preview.setFixedHeight(90)
        self._thumbnail_original = None
        self.thumbnail_label.setPixmap(QPixmap())
        self.thumbnail_label.setText("No preview")
        self._schedule_window_resize()

    def _format_meta_value(self, value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else "-"
        if isinstance(value, (list, tuple, set)):
            parts = [str(item) for item in value if item not in (None, "")]
            return ", ".join(parts) if parts else "-"
        return str(value)

    def _format_duration_value(self, value: Any) -> str:
        total_seconds: Optional[int] = None

        if isinstance(value, (int, float)) and value >= 0:
            total_seconds = int(value)
        elif isinstance(value, str):
            stripped = value.strip()
            if stripped.isdigit():
                total_seconds = int(stripped)
            elif ":" in stripped:
                parts = stripped.split(":")
                if all(part.isdigit() for part in parts):
                    try:
                        nums = [int(part) for part in parts]
                        if len(nums) == 2:
                            total_seconds = nums[0] * 60 + nums[1]
                        elif len(nums) == 3:
                            total_seconds = nums[0] * 3600 + nums[1] * 60 + nums[2]
                    except Exception:
                        total_seconds = None

        if total_seconds is None:
            return self._format_meta_value(value)

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _format_upload_date_value(self, value: Any) -> str:
        text = self._format_meta_value(value)
        if text == "-":
            return text

        stripped = text.strip()
        if len(stripped) == 8 and stripped.isdigit():
            return f"{stripped[0:4]}-{stripped[4:6]}-{stripped[6:8]}"
        return stripped

    def _render_metadata_html(self, info: dict[str, Any]) -> str:
        rows: list[tuple[str, str]] = [
            ("id", self._format_meta_value(info.get("id"))),
            ("title", self._format_meta_value(info.get("title"))),
            ("uploader", self._format_meta_value(info.get("uploader") or info.get("channel") or info.get("creator"))),
            ("duration", self._format_duration_value(info.get("duration") or info.get("duration_string"))),
            ("upload_date", self._format_upload_date_value(info.get("upload_date"))),
            ("extractor", self._format_meta_value(info.get("extractor"))),
            ("url", self._format_meta_value(info.get("webpage_url") or info.get("original_url"))),
        ]

        parts = [
            '<div style="line-height: 1.45;">',
        ]
        for key, raw_value in rows:
            value = escape(raw_value).replace("\n", "<br>")
            parts.append(
                f'<div style="margin: 0 0 4px 0;"><b>{escape(key)}</b>: '
                f'<span style="word-break: break-word;">{value}</span></div>'
            )
        parts.append('</div>')
        return "".join(parts)

    def _select_thumbnail_source(self, info: dict[str, Any]) -> Optional[str]:
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

    def _load_pixmap_from_source(self, source: str) -> Optional[QPixmap]:
        try:
            if source.startswith(("http://", "https://")):
                with urllib.request.urlopen(source, timeout=8) as response:
                    data = response.read()
            elif os.path.exists(source):
                with open(source, "rb") as file_obj:
                    data = file_obj.read()
            else:
                return None

            pixmap = QPixmap()
            if not pixmap.loadFromData(data):
                return None
            return pixmap
        except Exception:
            return None

    def _set_thumbnail_preview(self, info: dict[str, Any]) -> None:
        source = self._select_thumbnail_source(info)
        if not source:
            self._thumbnail_original = None
            self.thumbnail_label.setPixmap(QPixmap())
            self.thumbnail_label.setText("No preview")
            return

        pixmap = self._load_pixmap_from_source(source)
        if pixmap is None or pixmap.isNull():
            self.thumbnail_label.setPixmap(QPixmap())
            self.thumbnail_label.setText("Preview недоступно")
            self._thumbnail_original = None
            return

        self._thumbnail_original = pixmap
        self._apply_thumbnail_preview()

    def _apply_thumbnail_preview(self) -> None:
        if self._thumbnail_original is None or self._thumbnail_original.isNull():
            return

        scaled = self._thumbnail_original.scaled(
            self.thumbnail_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail_label.setText("")
        self.thumbnail_label.setPixmap(scaled)

    def _render_metadata(self, info: dict[str, Any]) -> None:
        self.meta_preview.setHtml(self._render_metadata_html(info))
        self._set_thumbnail_preview(info)
        self._sync_meta_preview_height()
        # Удалена строка: self.meta_preview.document().adjustSize()
        self.meta_card.adjustSize()
        self._schedule_window_resize()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_thumbnail_preview()
        self._sync_meta_preview_height()

    def perform_link_check(self) -> None:
        url = self.url_input.text().strip()

        if not url:
            self.check_label.setText("Enter URL")
            self.clear_metadata_panel()
            return

        cookies = self.cookies_input.text().strip() or None

        self._stop_link_checker()
        self.link_checker = LinkCheckWorker(url, cookies)
        self.link_checker.checked.connect(self._handle_link_checked)
        self.link_checker.status.connect(self.log)
        self.link_checker.start()

    def populate_formats_from_info(self, info: dict[str, Any]) -> None:
        self.format_select.clear()

        try:
            formats = [
                fmt for fmt in info.get("formats", [])
                if isinstance(fmt, dict) and fmt.get("vcodec") != "none"
            ]

            formats.sort(
                key=lambda fmt: (
                    fmt.get("height") or 0,
                    fmt.get("fps") or 0,
                    fmt.get("tbr") or 0,
                ),
                reverse=True,
            )

            for fmt in formats:
                fmt_id = fmt.get("format_id")
                if fmt_id is None:
                    continue

                height = fmt.get("height") or "?"
                fps = fmt.get("fps")
                note = fmt.get("format_note") or ""

                label = f"{fmt_id} {height}p"
                if fps:
                    label += f" {fps}fps"
                if note:
                    label += f" {note}"

                self.format_select.addItem(label, fmt_id)

            visible = self.format_select.count() > 0
            self.format_label.setVisible(visible)
            self.format_select.setVisible(visible)

            if visible:
                self.format_select.setCurrentIndex(0)
            else:
                self.log("No video formats found")

        except Exception as exc:
            self.log(f"Format error: {exc}")
            self.format_label.hide()
            self.format_select.hide()

    def update_format_options(self, *_args: object) -> None:
        if self.type_select.currentText() == "video" and self.current_info:
            self.populate_formats_from_info(self.current_info)
        else:
            self.format_select.clear()
            self.format_label.hide()
            self.format_select.hide()

    def toggle_pause_download(self) -> None:
        worker = self.worker
        if not worker or not worker.isRunning():
            return

        if worker.is_paused():
            worker.resume()
            self._set_pause_button_state(False)
            self.log("Download resumed")
        else:
            worker.pause()
            self._set_pause_button_state(True)
            self.log("Download paused")

    def cancel_download(self) -> None:
        worker = self.worker
        if not worker or not worker.isRunning():
            return

        self._download_cancelled = True
        self.cancel_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.log("Cancel загрузки...")
        try:
            worker.cancel()
        except Exception:
            try:
                worker.resume()
            except Exception:
                pass
            worker.requestInterruption()

    def start_download(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        url = self.url_input.text().strip()
        if not url:
            self.log("Enter URL")
            return

        ffmpeg = self.ffmpeg_input.text().strip() or None
        cookies = self.cookies_input.text().strip() or None
        mode = self.type_select.currentText()

        selected_format = None
        if mode == "video" and self.format_select.count() > 0:
            selected_format = self.format_select.currentData()

        base_dir = "dl"
        os.makedirs(base_dir, exist_ok=True)

        self._download_cancelled = False
        self.worker = DownloadWorker(
            url=url,
            mode=mode,
            base_dir=base_dir,
            selected_format=selected_format,
            ffmpeg_path=ffmpeg,
            cookies_path=cookies,
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.log)
        self.worker.finished.connect(self._handle_download_finished)

        self.progress_bar.setValue(0)
        self._set_busy_state(True)
        self.download_button.setText("Working...")
        self._set_pause_button_state(False)
        self.worker.start()
