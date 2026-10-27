"""Runtime inventory — stock counts and 86 toggles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from menu_engine.db.models import PROJECT_ROOT
from menu_engine.menu.loader import load_menu_from_path, reset_menu_cache
from menu_engine.utils.file_ops import atomic_write_json


INVENTORY_PATH = PROJECT_ROOT / "data" / "inventory.json"


def _load_inventory() -> dict[str, Any]:
    if not INVENTORY_PATH.exists():
        return {"items": {}, "modifiers": {}}
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _save_inventory(data: dict[str, Any]) -> None:
    atomic_write_json(INVENTORY_PATH, data)


def get_inventory_status() -> dict[str, Any]:
    inv = _load_inventory()
    menu_path = PROJECT_ROOT / "data" / "menu" / "pizza-menu.json"
    menu = load_menu_from_path(menu_path)
    items = []
    for item in menu["items"]:
        stock = inv["items"].get(item["id"], {"stock": None, "is_86d": not item.get("is_available", True)})
        items.append(
            {
                "id": item["id"],
                "name": item["name"],
                "is_available": item.get("is_available", True),
                "stock": stock.get("stock"),
                "low_stock": stock.get("stock") is not None and stock.get("stock", 99) < 5,
            }
        )
    modifiers = []
    for mod in menu["modifiers"]:
        stock = inv["modifiers"].get(mod["id"], {"stock": None, "is_86d": mod.get("is_86d", False)})
        modifiers.append(
            {
                "id": mod["id"],
                "name": mod["name"],
                "group": mod.get("group"),
                "is_86d": mod.get("is_86d", False),
                "stock": stock.get("stock"),
            }
        )
    return {"items": items, "modifiers": modifiers}


def toggle_item_availability(item_id: str, available: bool) -> dict[str, Any]:
    menu_path = PROJECT_ROOT / "data" / "menu" / "pizza-menu.json"
    menu = load_menu_from_path(menu_path)
    found = False
    for item in menu["items"]:
        if item["id"] == item_id:
            item["is_available"] = available
            found = True
            break
    if not found:
        raise ValueError(f"Item {item_id} not found")
    atomic_write_json(menu_path, menu)
    reset_menu_cache()
    return {"id": item_id, "is_available": available}


def toggle_modifier_86(modifier_id: str, is_86d: bool) -> dict[str, Any]:
    menu_path = PROJECT_ROOT / "data" / "menu" / "pizza-menu.json"
    menu = load_menu_from_path(menu_path)
    found = False
    for mod in menu["modifiers"]:
        if mod["id"] == modifier_id:
            mod["is_86d"] = is_86d
            found = True
            break
    if not found:
        raise ValueError(f"Modifier {modifier_id} not found")
    atomic_write_json(menu_path, menu)
    reset_menu_cache()
    inv = _load_inventory()
    inv.setdefault("modifiers", {})[modifier_id] = {"is_86d": is_86d}
    _save_inventory(inv)
    return {"id": modifier_id, "is_86d": is_86d}


def decrement_stock(menu_item_ids: list[str]) -> None:
    inv = _load_inventory()
    for item_id in menu_item_ids:
        entry = inv.setdefault("items", {}).setdefault(item_id, {"stock": None})
        if entry.get("stock") is not None:
            entry["stock"] = max(0, entry["stock"] - 1)
            if entry["stock"] == 0:
                toggle_item_availability(item_id, False)
    _save_inventory(inv)
