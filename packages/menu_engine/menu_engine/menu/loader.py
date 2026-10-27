from __future__ import annotations

import json
import re
from pathlib import Path

from menu_engine.types import MenuData, ToppingSelection

_cached_menu: MenuData | None = None

_SIZE_ALIASES: dict[str, str] = {
    "regular": "regular",
    "small": "small",
    "medium": "medium",
    "large": "large",
    "med": "medium",
    "lg": "large",
    "sm": "small",
}


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def resolve_item(menu: MenuData, query: str) -> dict | None:
    """Resolve a customer-facing item name (or legacy slug id) to a menu item."""
    if not query or not str(query).strip():
        return None

    raw = str(query).strip()
    by_id = get_item(menu, raw)
    if by_id:
        return by_id

    lowered = raw.lower()
    exact_name = next((item for item in menu["items"] if item["name"].lower() == lowered), None)
    if exact_name:
        return exact_name

    normalized = _normalize_label(raw)
    normalized_matches = [
        item
        for item in menu["items"]
        if _normalize_label(item["name"]) == normalized or _normalize_label(item["id"]) == normalized
    ]
    if len(normalized_matches) == 1:
        return normalized_matches[0]

    partial_matches = [
        item
        for item in menu["items"]
        if normalized in _normalize_label(item["name"]) or _normalize_label(item["name"]) in normalized
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    return None


def resolve_size(menu: MenuData, item_id: str, size_query: str) -> str | None:
    """Resolve spoken size labels like 'medium' to a menu size id for the item."""
    item = get_item(menu, item_id)
    if not item or not size_query:
        return None

    raw = str(size_query).strip().lower()
    if raw in item["sizes"]:
        return raw

    alias = _SIZE_ALIASES.get(raw)
    if alias and alias in item["sizes"]:
        return alias

    for size_id in item["sizes"]:
        size = get_size(menu, size_id)
        if size and size["name"].lower() == raw:
            return size_id
        if size and _normalize_label(size["name"]) == _normalize_label(raw):
            return size_id
    return None


def default_size_for_item(menu: MenuData, item_id: str) -> str | None:
    item = get_item(menu, item_id)
    if not item:
        return None
    for candidate in ("regular", "medium", "small", "large"):
        if candidate in item["sizes"]:
            return candidate
    return next(iter(item["sizes"]), None)


def get_default_menu_path() -> Path:
    return Path(__file__).resolve().parents[4] / "data" / "menu" / "pizza-menu.json"


def load_menu_from_path(path: str | Path) -> MenuData:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_menu(path: str | Path | None = None) -> MenuData:
    global _cached_menu
    if path is None and _cached_menu is not None:
        return _cached_menu
    menu_path = Path(path) if path else get_default_menu_path()
    menu = load_menu_from_path(menu_path)
    if path is None:
        _cached_menu = menu
    return menu


def reset_menu_cache() -> None:
    global _cached_menu
    _cached_menu = None


def get_item(menu: MenuData, item_id: str) -> dict | None:
    return next((i for i in menu["items"] if i["id"] == item_id), None)


def get_modifier(menu: MenuData, modifier_id: str) -> dict | None:
    return next((m for m in menu["modifiers"] if m["id"] == modifier_id), None)


def get_size(menu: MenuData, size_id: str) -> dict | None:
    return next((s for s in menu["sizes"] if s["id"] == size_id), None)


def get_modifier_name(menu: MenuData, modifier_id: str) -> str:
    mod = get_modifier(menu, modifier_id)
    return mod["name"] if mod else modifier_id


def format_toppings(menu: MenuData, toppings: list[ToppingSelection | dict]) -> str:
    if not toppings:
        return "plain"
    parts = []
    for t in toppings:
        if isinstance(t, dict):
            mod_id = t["modifier_id"]
            extra = t.get("extra", False)
        else:
            mod_id = t.modifier_id
            extra = t.extra
        name = get_modifier_name(menu, mod_id)
        parts.append(f"extra {name}" if extra else name)
    return ", ".join(parts)
