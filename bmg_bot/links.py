from __future__ import annotations

_LINK_MARKERS = (
    "http",
    "https",
    "t.me",
    "telegram.me",
    ".com",
    ".net",
    ".org",
    "www.",
)


def text_contains_link(text: str) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in _LINK_MARKERS)
