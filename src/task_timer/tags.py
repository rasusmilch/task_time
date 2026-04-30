"""Tag helpers."""
from __future__ import annotations

import re

_WS=re.compile(r"\s+")

def normalize_tag(raw: str) -> str:
    key = _WS.sub(" ", raw.strip().casefold())
    if not key:
        raise ValueError("Tag is required")
    if any(ord(ch) < 32 for ch in key):
        raise ValueError("Tag cannot contain control characters")
    return key

def normalize_tag_list(values: list[str] | set[str]) -> list[str]:
    out=[]
    seen=set()
    for value in values:
        key=normalize_tag(value)
        if key in seen:
            raise ValueError(f"Duplicate tag: {key}")
        seen.add(key)
        out.append(key)
    return sorted(out)
