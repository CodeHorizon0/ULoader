from __future__ import annotations

from typing import Any, Mapping


def on_url_changed(self, _text: str) -> None:
    self.check_label.setText("Checking...")
    if hasattr(self, "clear_metadata_panel"):
        self.clear_metadata_panel()
    self.format_select.clear()
    self.format_label.hide()
    self.format_select.hide()
    self.progress_bar.setValue(0)
    self.debounce_timer.start(700)


def on_link_checked(self, valid: bool, info: Mapping[str, Any]) -> None:
    if valid:
        self.check_label.setText("Link is valid")
        self.current_info = dict(info) if info else {}

        if hasattr(self, "_render_metadata"):
            self._render_metadata(self.current_info)
        else:
            vid = self.current_info.get("id", "")
            title = self.current_info.get("title", "")
            uploader = self.current_info.get("uploader", "")
            duration = self.current_info.get("duration", "")
            webpage_url = self.current_info.get("webpage_url", "")

            self.meta_preview.setPlainText(
                f"id: {vid}\n"
                f"title: {title}\n"
                f"uploader: {uploader}\n"
                f"duration: {duration}\n"
                f"url: {webpage_url}"
            )

        if self.type_select.currentText() == "video":
            self.populate_formats_from_info(self.current_info)
    else:
        self.check_label.setText("Link is invalid")
        self.current_info = None
        if hasattr(self, "clear_metadata_panel"):
            self.clear_metadata_panel()
        else:
            self.meta_preview.clear()
        self.format_select.clear()
        self.format_select.hide()
        self.format_label.hide()


def on_download_finished(self) -> None:
    self._set_idle_state()
    self.log("Background tasks finished")
