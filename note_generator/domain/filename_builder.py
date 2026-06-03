from __future__ import annotations

import re
from pathlib import Path


_WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
}


class FilenameBuilder:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir

    def build(self, title: str) -> str:
        slug = self._sanitize_title(title)
        candidate = f"{slug}.md"
        if not (self._output_dir / candidate).exists():
            return candidate

        counter = 2
        while True:
            collision_name = f"{slug}-{counter}.md"
            if not (self._output_dir / collision_name).exists():
                return collision_name
            counter += 1

    def _sanitize_title(self, title: str) -> str:
        normalized = re.sub(r"[\x00-\x1f]", " ", title)
        normalized = re.sub(r'[\\/:*?"<>|]+', " ", normalized).strip()
        normalized = re.sub(r"\s+", "-", normalized).strip("-. ")
        normalized = normalized[:80].strip("-. ")
        if not normalized:
            normalized = "untitled"

        if normalized.casefold() in _WINDOWS_RESERVED_NAMES:
            normalized = f"{normalized}-note"
        return normalized
