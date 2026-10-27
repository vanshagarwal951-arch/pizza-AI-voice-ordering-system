from __future__ import annotations

from menu_engine.menu.loader import get_item, get_modifier, get_size
from menu_engine.pricing import calculate_line_total
from menu_engine.types import (
    AddItemInput,
    MenuData,
    ToppingSelection,
    ValidatedOrder,
    ValidationError,
)


def _validate_item_exists(menu: MenuData, item_id: str) -> ValidationError | None:
    item = get_item(menu, item_id)
    if not item:
        return ValidationError(
            "R01",
            f'Sorry, we don\'t have that on the menu. Could you pick something else?',
        )
    if not item.get("is_available", True):
        return ValidationError(
            "R01",
            "This item is not available please order something else",
        )
    return None


def _validate_size(menu: MenuData, item_id: str, size_id: str) -> ValidationError | None:
    item = get_item(menu, item_id)
    if not item:
        return None
    size = get_size(menu, size_id)
    if not size:
        return ValidationError("R02", f'Sorry, "{size_id}" is not a valid size.')
    if size_id not in item["sizes"]:
        available = ", ".join(item["sizes"].keys())
        return ValidationError(
            "R02",
            f"Sorry, {size['name']} is not available for {item['name']}. Available sizes: {available}.",
        )
    return None


def _validate_topping(
    menu: MenuData, topping: ToppingSelection, allowed_groups: list[str]
) -> ValidationError | None:
    mod = get_modifier(menu, topping.modifier_id)
    if not mod:
        return ValidationError("R03", f'Sorry, we don\'t have "{topping.modifier_id}" as a topping.')
    if mod.get("is_86d"):
        return ValidationError("R03", f"Sorry, {mod['name']} is 86'd tonight — we're out of stock.")

    group_allowed = (
        "whole_toppings" in allowed_groups
        or "toppings_left" in allowed_groups
        or "toppings_right" in allowed_groups
        or mod["group"] in allowed_groups
    )
    if not group_allowed and mod["group"] == "toppings":
        return ValidationError("R04", f"Sorry, you can't add {mod['name']} to this item.")
    if mod["group"] in ("crust", "sauce") and mod["group"] not in allowed_groups:
        return ValidationError("R04", f"Sorry, {mod['name']} is not an option for this item.")
    return None


def _validate_no_duplicates(toppings: list[ToppingSelection], side: str) -> ValidationError | None:
    seen: set[str] = set()
    for t in toppings:
        if t.modifier_id in seen:
            return ValidationError(
                "R08", f"Sorry, you can't add the same topping twice on the {side} side."
            )
        seen.add(t.modifier_id)
    return None


def _validate_half_and_half(menu: MenuData, input: AddItemInput) -> ValidationError | None:
    rules = menu["rules"]["half_and_half"]
    left = input.left_toppings
    right = input.right_toppings

    if rules["requires_both_sides"] and (not left or not right):
        return ValidationError(
            "R05",
            "For a half-and-half pizza, I need toppings on both sides. "
            "Which toppings would you like on each half?",
        )
    max_per = rules["max_toppings_per_side"]
    if len(left) > max_per:
        return ValidationError(
            "R06",
            f"Sorry, you can only have up to {max_per} toppings per side. You have {len(left)} on the left.",
        )
    if len(right) > max_per:
        return ValidationError(
            "R06",
            f"Sorry, you can only have up to {max_per} toppings per side. You have {len(right)} on the right.",
        )
    return None


def validate_add_item(
    menu: MenuData, input: AddItemInput
) -> tuple[bool, ValidatedOrder | None, ValidationError | None]:
    item_error = _validate_item_exists(menu, input.menu_item_id)
    if item_error:
        return False, None, item_error

    size_error = _validate_size(menu, input.menu_item_id, input.size_id)
    if size_error:
        return False, None, size_error

    item = get_item(menu, input.menu_item_id)
    size = get_size(menu, input.size_id)
    assert item and size

    left = input.left_toppings
    right = input.right_toppings
    whole = input.whole_toppings

    if input.is_half_and_half:
        hh_error = _validate_half_and_half(menu, input)
        if hh_error:
            return False, None, hh_error
        for t in left:
            err = _validate_topping(menu, t, item["modifier_groups"])
            if err:
                return False, None, err
        for t in right:
            err = _validate_topping(menu, t, item["modifier_groups"])
            if err:
                return False, None, err
        dup_left = _validate_no_duplicates(left, "left")
        if dup_left:
            return False, None, dup_left
        dup_right = _validate_no_duplicates(right, "right")
        if dup_right:
            return False, None, dup_right
    else:
        if left or right:
            return False, None, ValidationError(
                "R05",
                "For a whole pizza, please use whole_toppings instead of left/right sides.",
            )
        max_whole = menu["rules"]["max_whole_toppings"]
        if len(whole) > max_whole:
            return False, None, ValidationError(
                "R06",
                f"Sorry, you can only have up to {max_whole} toppings on a whole pizza.",
            )
        for t in whole:
            err = _validate_topping(menu, t, item["modifier_groups"])
            if err:
                return False, None, err
        dup_whole = _validate_no_duplicates(whole, "whole")
        if dup_whole:
            return False, None, dup_whole

    if input.crust_id:
        crust_err = _validate_topping(
            menu, ToppingSelection(input.crust_id), item["modifier_groups"]
        )
        if crust_err:
            return False, None, crust_err

    line_total = calculate_line_total(
        menu,
        menu_item_id=input.menu_item_id,
        size_id=input.size_id,
        is_half_and_half=input.is_half_and_half,
        left_toppings=left,
        right_toppings=right,
        whole_toppings=whole,
        crust_id=input.crust_id,
        quantity=input.quantity,
    )

    order = ValidatedOrder(
        menu_item_id=input.menu_item_id,
        menu_item_name=item["name"],
        size_id=input.size_id,
        size_name=size["name"],
        is_half_and_half=input.is_half_and_half,
        left_toppings=left,
        right_toppings=right,
        whole_toppings=whole,
        crust_id=input.crust_id,
        line_total_cents=line_total,
        quantity=input.quantity,
    )
    return True, order, None


def validate_remove_item(cart_item_id: str, existing_ids: list[str]) -> ValidationError | None:
    if cart_item_id not in existing_ids:
        return ValidationError(
            "R10",
            "I can't find that item in your cart. Would you like me to read back your order?",
        )
    return None
