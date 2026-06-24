from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_PLAYLIST_PARAMS = {"list", "index", "start_radio", "pp"}


def normalize_single_media_url(url: str) -> str:
    """Return a media URL without playlist-specific query parameters.

    The project only downloads a single item, so playlist selectors should be
    stripped from shared watch links such as YouTube URLs.
    """
    text = url.strip()
    if not text:
        return text

    parts = urlsplit(text)
    host = parts.netloc.lower()
    if "youtube.com" not in host and "youtu.be" not in host:
        return text

    query_items = parse_qsl(parts.query, keep_blank_values=True)
    if not query_items:
        return text

    filtered = [(key, value) for key, value in query_items if key not in _PLAYLIST_PARAMS]
    if filtered == query_items:
        return text

    new_query = urlencode(filtered, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
