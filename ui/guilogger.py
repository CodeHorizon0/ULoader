from __future__ import annotations

from typing import Callable

from utils.filters import clean_ansi


class GuiLogger:
    def __init__(self, emit_func: Callable[[str], None]) -> None:
        self._emit = emit_func

    def debug(self, msg) -> None:
        self._emit(clean_ansi(msg))

    def info(self, msg) -> None:
        self._emit(clean_ansi(msg))

    def warning(self, msg) -> None:
        self._emit(clean_ansi(msg))

    def error(self, msg) -> None:
        self._emit(clean_ansi(msg))
