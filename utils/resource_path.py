from __future__ import annotations

import os
import sys
from typing import Iterable


def _unique_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def _get_base_candidates() -> list[str]:
    candidates: list[str] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str) and meipass:
        candidates.append(meipass)

    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))

    candidates.append(os.path.abspath("."))

    try:
        candidates.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass

    return _unique_paths(candidates)


def resource_path(relative_path: str) -> str:
    """
    Returns an absolute path to a bundled or local resource.
    """
    if not relative_path:
        raise ValueError("relative_path must not be empty")

    for base in _get_base_candidates():
        candidate = os.path.abspath(os.path.join(base, relative_path))
        if os.path.exists(candidate):
            return candidate

    tried_paths = [
        os.path.abspath(os.path.join(base, relative_path))
        for base in _get_base_candidates()
    ]
    raise FileNotFoundError(
        f"Resource '{relative_path}' not found in any candidate path:\n" +
        "\n".join(f"  - {path}" for path in tried_paths)
    )
