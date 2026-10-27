"""Menu administration — price updates and item edits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from menu_engine.db.models import PROJECT_ROOT
from menu_engine.menu.loader import load_menu_from_path, reset_menu_cache
from menu_engine.utils.file_ops import atomic_write_json


def get_menu_path() -> Path:
    return PROJECT_ROOT / "data" / "menu" / "pizza-menu.json"


def update_item_price(item_id: str, size_id: str, price_cents: int) -> dict[str, Any]:
    menu_path = get_menu_path()
    menu = load_menu_from_path(menu_path)
    for item in menu["items"]:
        if item["id"] == item_id:
            if size_id not in item["sizes"]:
                raise ValueError(f"Size {size_id} not found on {item_id}")
            item["sizes"][size_id]["base_price_cents"] = price_cents
            atomic_write_json(menu_path, menu)
            reset_menu_cache()
            return {"item_id": item_id, "size_id": size_id, "price_cents": price_cents}
    raise ValueError(f"Item {item_id} not found")


def update_restaurant_settings(settings: dict[str, Any]) -> dict[str, Any]:
    menu_path = get_menu_path()
    menu = load_menu_from_path(menu_path)
    menu["restaurant"].update(settings)
    atomic_write_json(menu_path, menu)
    reset_menu_cache()
    return menu["restaurant"]
