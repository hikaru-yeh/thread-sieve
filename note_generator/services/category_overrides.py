from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryOverride:
    category: str
    keywords: tuple[str, ...] = ()
    regexes: tuple[str, ...] = ()


def parse_category_overrides(config_data: dict) -> list[CategoryOverride]:
    raw_overrides = config_data.get("category-overrides", [])
    if not isinstance(raw_overrides, list):
        return []

    overrides: list[CategoryOverride] = []
    for raw_override in raw_overrides:
        if not isinstance(raw_override, dict):
            continue

        category = str(raw_override.get("category", "")).strip()
        if not category:
            continue

        overrides.append(
            CategoryOverride(
                category=category,
                keywords=tuple(_read_str_list(raw_override.get("keywords", []))),
                regexes=tuple(_read_str_list(raw_override.get("regex", raw_override.get("regexes", [])))),
            )
        )
    return overrides


def detect_forced_category(
    text: str,
    overrides: Collection[CategoryOverride],
    categories: Collection[str],
) -> str:
    category_set = set(categories)
    raw_text = str(text or "")
    lowered = raw_text.casefold()

    for override in overrides:
        if override.category not in category_set:
            continue
        if any(keyword.casefold() in lowered for keyword in override.keywords):
            return override.category
        if any(_regex_matches(pattern, raw_text) for pattern in override.regexes):
            return override.category

    return ""


def _read_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _regex_matches(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    except re.error:
        return False
