from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

ErrorCode = Literal["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10"]


@dataclass
class ToppingSelection:
    modifier_id: str
    extra: bool = False


@dataclass
class AddItemInput:
    menu_item_id: str
    size_id: str
    is_half_and_half: bool = False
    left_toppings: list[ToppingSelection] = field(default_factory=list)
    right_toppings: list[ToppingSelection] = field(default_factory=list)
    whole_toppings: list[ToppingSelection] = field(default_factory=list)
    crust_id: Optional[str] = None
    quantity: int = 1


@dataclass
class ValidationError:
    code: ErrorCode
    message: str


@dataclass
class ValidatedOrder:
    menu_item_id: str
    menu_item_name: str
    size_id: str
    size_name: str
    is_half_and_half: bool
    left_toppings: list[ToppingSelection]
    right_toppings: list[ToppingSelection]
    whole_toppings: list[ToppingSelection]
    line_total_cents: int
    quantity: int
    crust_id: Optional[str] = None


@dataclass
class CartLineItem:
    id: str
    menu_item_id: str
    menu_item_name: str
    size_id: str
    size_name: str
    is_half_and_half: bool
    left_toppings: list[ToppingSelection]
    right_toppings: list[ToppingSelection]
    whole_toppings: list[ToppingSelection]
    line_total_cents: int
    quantity: int
    crust_id: Optional[str] = None


@dataclass
class CartSummary:
    items: list[CartLineItem]
    item_count: int
    total_cents: int
    currency: str
    spoken_summary: str


@dataclass
class ToolResult:
    success: bool
    message: str
    cart_item_id: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    cart_summary: Optional[CartSummary] = None


# Menu JSON shapes (dict-based for loader)
MenuData = dict
