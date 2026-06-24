from __future__ import annotations

import re

ANSI_ESCAPE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
SAFE_FILENAME = re.compile(r'[\\/*?:"<>|]')


def clean_ansi(text: object) -> str:
    return ANSI_ESCAPE.sub("", str(text))


def safe_filename(name: object) -> str:
    """Превращает имя файла в безопасное для ОС."""
    return SAFE_FILENAME.sub("_", str(name)).strip().strip(".")
