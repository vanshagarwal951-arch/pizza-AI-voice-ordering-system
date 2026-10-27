from __future__ import annotations

import uuid

from menu_engine.menu.loader import format_toppings
from menu_engine.pricing import format_cents, format_spoken_amount
from menu_engine.types import CartLineItem, CartSummary, MenuData, ValidatedOrder


class Cart:
    def __init__(self) -> None:
        self._items: list[CartLineItem] = []

    def add(self, order: ValidatedOrder) -> CartLineItem:
        line = CartLineItem(
            id=str(uuid.uuid4()),
            menu_item_id=order.menu_item_id,
            menu_item_name=order.menu_item_name,
            size_id=order.size_id,
            size_name=order.size_name,
            is_half_and_half=order.is_half_and_half,
            left_toppings=list(order.left_toppings),
            right_toppings=list(order.right_toppings),
            whole_toppings=list(order.whole_toppings),
            crust_id=order.crust_id,
            line_total_cents=order.line_total_cents,
            quantity=order.quantity,
        )
        self._items.append(line)
        return line

    def remove(self, cart_item_id: str) -> bool:
        for idx, item in enumerate(self._items):
            if item.id == cart_item_id:
                self._items.pop(idx)
                return True
        return False

    def get_item_ids(self) -> list[str]:
        return [i.id for i in self._items]

    def get_items(self) -> list[CartLineItem]:
        return list(self._items)

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def summarize(self, menu: MenuData) -> CartSummary:
        total = sum(i.line_total_cents for i in self._items)
        spoken = self._build_spoken_summary(menu, total)
        return CartSummary(
            items=self.get_items(),
            item_count=len(self._items),
            total_cents=total,
            currency=menu["restaurant"]["currency"],
            spoken_summary=spoken,
        )

    def _build_spoken_summary(self, menu: MenuData, total: int) -> str:
        if not self._items:
            return "Your cart is empty."
        lines = []
        for idx, item in enumerate(self._items, start=1):
            desc = f"{item.size_name} {item.menu_item_name}"
            if item.is_half_and_half:
                left = format_toppings(menu, item.left_toppings)
                right = format_toppings(menu, item.right_toppings)
                desc += f", half {left} and half {right}"
            elif item.whole_toppings:
                desc += f" with {format_toppings(menu, item.whole_toppings)}"
            if item.quantity > 1:
                desc += f" x{item.quantity}"
            currency = menu["restaurant"]["currency"]
            desc += f" — {format_spoken_amount(item.line_total_cents, currency)}"
            lines.append(f"{idx}. {desc}")
        currency = menu["restaurant"]["currency"]
        return f"{'. '.join(lines)}. Total: {format_spoken_amount(total, currency)}."


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Cart] = {}

    def get_or_create(self, session_id: str) -> Cart:
        if session_id not in self._sessions:
            self._sessions[session_id] = Cart()
        return self._sessions[session_id]

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


default_session_manager = SessionManager()
