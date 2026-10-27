from __future__ import annotations

from menu_engine.menu.loader import get_modifier
from menu_engine.types import MenuData, ToppingSelection

EXTRA_MULTIPLIER = 1.5


def calculate_topping_price(menu: MenuData, toppings: list[ToppingSelection]) -> int:
    total = 0
    for t in toppings:
        mod = get_modifier(menu, t.modifier_id)
        if not mod:
            continue
        total += int(mod["price_cents"] * EXTRA_MULTIPLIER + 0.5) if t.extra else mod["price_cents"]
    return total


def calculate_line_total(
    menu: MenuData,
    *,
    menu_item_id: str,
    size_id: str,
    is_half_and_half: bool,
    left_toppings: list[ToppingSelection],
    right_toppings: list[ToppingSelection],
    whole_toppings: list[ToppingSelection],
    crust_id: str | None = None,
    quantity: int = 1,
) -> int:
    item = next((i for i in menu["items"] if i["id"] == menu_item_id), None)
    if not item:
        return 0
    size_pricing = item["sizes"].get(size_id)
    if not size_pricing:
        return 0

    line_total = size_pricing["base_price_cents"]
    if crust_id:
        crust = get_modifier(menu, crust_id)
        if crust:
            line_total += crust["price_cents"]

    if is_half_and_half:
        line_total += calculate_topping_price(menu, left_toppings)
        line_total += calculate_topping_price(menu, right_toppings)
    else:
        line_total += calculate_topping_price(menu, whole_toppings)

    return line_total * quantity


def calculate_order_totals(subtotal_cents: int, menu: dict) -> dict[str, int]:
    """Apply tax and delivery fee from restaurant config."""
    restaurant = menu.get("restaurant", {})
    tax_pct = float(restaurant.get("tax_percent", 5))
    delivery = int(restaurant.get("delivery_fee_cents", 0))
    tax = int(subtotal_cents * tax_pct / 100 + 0.5)
    total = subtotal_cents + tax + delivery
    return {
        "subtotal_cents": subtotal_cents,
        "tax_cents": tax,
        "delivery_fee_cents": delivery,
        "total_cents": total,
    }


def format_cents(cents: int, currency: str = "USD") -> str:
    amount = cents / 100
    if currency == "INR":
        return f"₹{int(amount)}/-" if amount == int(amount) else f"₹{amount:.2f}"
    dollars = f"{amount:.2f}"
    return f"${dollars}" if currency == "USD" else f"{dollars} {currency}"


_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _int_to_words(n: int) -> str:
    if n < 0:
        return f"minus {_int_to_words(-n)}"
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, rem = divmod(n, 10)
        return _TENS[tens] if rem == 0 else f"{_TENS[tens]} {_ONES[rem]}"
    if n < 1000:
        hundreds, rem = divmod(n, 100)
        head = f"{_ONES[hundreds]} hundred"
        return head if rem == 0 else f"{head} {_int_to_words(rem)}"
    if n < 100_000:
        thousands, rem = divmod(n, 1000)
        head = f"{_int_to_words(thousands)} thousand"
        return head if rem == 0 else f"{head} {_int_to_words(rem)}"
    lakhs, rem = divmod(n, 100_000)
    head = f"{_int_to_words(lakhs)} lakh"
    return head if rem == 0 else f"{head} {_int_to_words(rem)}"


def format_spoken_amount(cents: int, currency: str = "USD") -> str:
    """TTS-friendly price text — avoids digits/symbols the LLM or TTS may misread."""
    major, minor = divmod(cents, 100)
    if currency == "INR":
        if minor:
            return f"{_int_to_words(major)} rupees and {_int_to_words(minor)} paise"
        return f"{_int_to_words(major)} rupees"
    if minor:
        return f"{_int_to_words(major)} dollars and {_int_to_words(minor)} cents"
    return f"{_int_to_words(major)} dollars"
