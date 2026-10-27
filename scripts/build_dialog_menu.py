"""Generate data/menu/pizza-menu.json for DIALOG cafe."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menu" / "pizza-menu.json"

BRAND = "DIALOG Pizza"


def rupees(amount: int) -> int:
    return amount * 100


def regular_item(
    item_id: str,
    name: str,
    category: str,
    price: int,
    *,
    description: str = "",
    modifier_groups: list[str] | None = None,
) -> dict:
    item: dict = {
        "id": item_id,
        "name": name,
        "category": category,
        "is_available": True,
        "sizes": {"regular": {"base_price_cents": rupees(price)}},
        "modifier_groups": modifier_groups or [],
    }
    if description:
        item["description"] = description
    return item


def pizza_item(
    item_id: str,
    name: str,
    category: str,
    prices: tuple[int, int, int],
    *,
    description: str = "",
    veg: bool = True,
) -> dict:
    s, m, l = prices
    item: dict = {
        "id": item_id,
        "name": name,
        "category": category,
        "is_available": True,
        "sizes": {
            "small": {"base_price_cents": rupees(s)},
            "medium": {"base_price_cents": rupees(m)},
            "large": {"base_price_cents": rupees(l)},
        },
        "modifier_groups": ["pizza_upgrade", "extra_toppings"],
    }
    if description:
        item["description"] = description
    item["tags"] = ["veg"] if veg else ["non-veg"]
    return item


def build_menu() -> dict:
    items: list[dict] = []

    # --- MOJITO - VOHITO ---
    for item_id, name, price in [
        ("virgin-mint-mojito", "Virgin Mint Mojito", 110),
        ("green-apple-mojito", "Green Apple Mojito", 110),
        ("cranberry-mojito", "Cranberry Mojito", 110),
        ("black-magic", "Black Magic", 110),
        ("bubble-gum-mojito", "Bubble Gum Mojito", 110),
        ("blue-curacao-mojito", "Blue Curacao Mojito", 110),
        ("kiwi-mojito", "Kiwi Mojito", 130),
        ("watermelon-mojito", "Water Melon Mojito", 130),
    ]:
        items.append(regular_item(item_id, name, "mojito-vohito", price))

    # --- ICED TEAS ---
    items += [
        regular_item(
            "lemon-mint-iced-tea",
            "Lemon Mint Iced Tea",
            "iced-teas",
            120,
            description="Beloved refreshing drink always",
        ),
        regular_item(
            "sparkling-peach-iced-tea",
            "Sparkling Peach Iced Tea",
            "iced-teas",
            120,
            description="Peach infused tea on the rocks with crushed peach fruit",
        ),
        regular_item("watermelon-iced-tea", "Water Melon Iced Tea", "iced-teas", 140),
    ]

    # --- SIDES ---
    items += [
        regular_item("french-fries", "French Fries", "sides", 150),
        regular_item("chicken-nuggets", "Chicken Nuggets", "sides", 160),
        regular_item("peri-peri-fries", "Peri-Peri Fries", "sides", 160),
        regular_item("masala-fries", "Masala Fries", "sides", 170),
        regular_item("zesty-c4-fries", "Zesty C4 Fries", "sides", 180),
        regular_item(
            "clucnk-n-crunch",
            "Clucnk N Crunch",
            "sides",
            250,
            description="Chicken wings, popcorn chicken & masala fries",
        ),
        regular_item("dialogs-chicken-bucket", "Dialog's Chicken Bucket", "sides", 550),
    ]

    # --- PASTAS ---
    items += [
        regular_item(
            "penne-alfredo",
            "Penne Alfredo",
            "pastas",
            200,
            description="Penne tossed with white sauce & garden vegetables",
            modifier_groups=["pasta_addon"],
        ),
        regular_item(
            "penne-arrabiata",
            "Penne Arrabiata",
            "pastas",
            200,
            description="Penne tossed with spicy red tomato sauce & garden vegetables",
            modifier_groups=["pasta_addon"],
        ),
        regular_item("zesty-pasta", "Zesty Pasta", "pastas", 220, modifier_groups=["pasta_addon"]),
        regular_item("pink-sauce-pasta", "Pink Sauce Pasta", "pastas", 220, modifier_groups=["pasta_addon"]),
        regular_item(
            "mushroom-sauce-pasta",
            "Mushroom Sauce Pasta",
            "pastas",
            220,
            modifier_groups=["pasta_addon"],
        ),
        regular_item("makhni-sauce-pasta", "Makhni Sauce Pasta", "pastas", 220, modifier_groups=["pasta_addon"]),
        regular_item(
            "pink-mushroom-sauce-pasta",
            "Pink Mushroom Sauce Pasta",
            "pastas",
            240,
            modifier_groups=["pasta_addon"],
        ),
        regular_item(
            "oven-baked-pasta",
            "Oven Baked Pasta",
            "pastas",
            250,
            description="Alfredo / Arrabiata / Makhni / Pink",
            modifier_groups=["pasta_addon"],
        ),
    ]

    # --- CRISPY TOASTIES ---
    items += [
        regular_item("cheese-garlic-bread", "Cheese Garlic Bread", "crispy-toasties", 110),
        regular_item("cheese-garlic-bread-sticks", "Cheese Garlic Bread Sticks", "crispy-toasties", 180),
    ]

    # --- SUBS ---
    items += [
        regular_item(
            "spicy-veg-sub",
            "Spicy Veg Sub",
            "subs",
            110,
            description="All veggies, without any patty",
        ),
        regular_item("aloo-tikki-sub", "Aloo Tikki Sub", "subs", 120, description="Potato patty filling"),
        regular_item(
            "hanging-green-sub",
            "Hanging Green Sub",
            "subs",
            130,
            description="Includes veggie patty",
        ),
        regular_item(
            "paneer-tikka-sub",
            "Paneer Tikka Sub",
            "subs",
            150,
            description="Paneer marinated in spices & grilled in a tandoor",
        ),
        regular_item(
            "chicken-tikka-sub",
            "Chicken Tikka Sub",
            "subs",
            150,
            description="Marinated & tandoor grilled chicken",
        ),
        regular_item(
            "chicken-seekh-sub",
            "Chicken Seekh Sub",
            "subs",
            150,
            description="Seekh kebab filling with chicken mince, onions & spices",
        ),
    ]

    # --- BURGERS ---
    items += [
        regular_item("aloo-tikki-burger", "Aloo Tikki Burger", "burgers", 90),
        regular_item("mc-veggie-burger", "Mc Veggie Burger", "burgers", 100),
        regular_item("super-freak-burger", "Super Freak Burger", "burgers", 110),
        regular_item("go-green-burger", "Go Green Burger", "burgers", 120),
        regular_item("crispy-chicken-burger", "Crispy Chicken Burger", "burgers", 120),
        regular_item("grilled-chicken-burger", "Grilled Chicken Burger", "burgers", 130),
        regular_item("crumby-chicken-burger", "Crumby Chicken Burger", "burgers", 130),
        regular_item("peri-peri-paneer-patty", "Peri Peri Paneer Patty", "burgers", 140),
        regular_item("korean-chicken-burger", "Korean Chicken Burger", "burgers", 150),
        regular_item(
            "extra-cheese-slices",
            "Extra Cheese Slices",
            "burgers",
            30,
            modifier_groups=["burger_addon"],
        ),
    ]

    # --- WRAPS ---
    items += [
        regular_item("aloo-tikki-wrap", "Aloo Tikki Wrap", "wraps", 110),
        regular_item("veggie-patty-wrap", "Veggie Patty Wrap", "wraps", 120),
        regular_item("paneer-tikka-wrap", "Paneer Tikka Wrap", "wraps", 140),
        regular_item("chicken-tikka-wrap", "Chicken Tikka Wrap", "wraps", 150),
        regular_item("chicken-seekh-wrap", "Chicken Seekh Wrap", "wraps", 150),
        regular_item("crispy-chicken-wrap", "Crispy Chicken Wrap", "wraps", 150),
    ]

    # --- DESSERTS ---
    items += [
        regular_item("choco-lava-cake", "Choco Lava Cake", "desserts", 110),
        regular_item(
            "choco-lava-cake-ice-cream",
            "Choco Lava Cake With Vanilla Ice-Cream",
            "desserts",
            140,
        ),
        regular_item("blueberry-cheese-cake", "Blue Berry Cheese Cake", "desserts", 200),
        regular_item("biscoff-cheese-cake", "Biscoff Cheese Cake", "desserts", 220),
    ]

    # --- COFFEES ---
    items += [
        regular_item("cafe-americano", "Café Americano", "coffees", 100, description="Black coffee"),
        regular_item(
            "happiness",
            "Happiness",
            "coffees",
            140,
            description="Cappuccino with freshly grounded coffee beans imported from Malta",
        ),
        regular_item(
            "cafe-latte",
            "Café Latte",
            "coffees",
            150,
            description="Creamier coffee with a vanilla shot",
        ),
        regular_item(
            "cafe-mocha",
            "Café Mocha",
            "coffees",
            150,
            description="Chocolaty sibling of café latte",
        ),
        regular_item(
            "hazelnut-latte",
            "Hazelnut Latte",
            "coffees",
            150,
            description="Hazelnut fusion with freshly grounded coffee beans",
        ),
        regular_item(
            "caramel-latte",
            "Caramel Latte",
            "coffees",
            150,
            description="Ye coffee hai ya toffee? Yum!",
        ),
    ]

    # --- HOT BEVERAGES ---
    items += [
        regular_item(
            "hot-chocolate",
            "Hot Chocolate",
            "hot-beverages",
            140,
            description="Hershey's cocoa with warm steamed milk & chocolate powder",
        ),
        regular_item(
            "nutella-hot-chocolate",
            "Nutella Hot Chocolate",
            "hot-beverages",
            160,
            description="Nutella lover's delight — warm without caffeine",
        ),
    ]

    # --- COLD COFFEES ---
    items += [
        regular_item(
            "cafe-dialog-frappe",
            "Café Dialog Frappe",
            "cold-coffees",
            110,
            description="Classic cold coffee sprinkled with choco chips",
        ),
        regular_item("irish-iced-frappe", "Irish Iced Frappe", "cold-coffees", 130),
        regular_item(
            "dialogs-dare-devil-frappe",
            "Dialog's Dare Devil Frappe",
            "cold-coffees",
            140,
            description="Dark chocolate with dark roasted coffee",
        ),
        regular_item(
            "crunchy-caramel-frappe",
            "Crunchy Caramel Frappe",
            "cold-coffees",
            140,
            description="Toffee iced frappe",
        ),
        regular_item(
            "hazelnut-frappe",
            "Hazelnut Frappe",
            "cold-coffees",
            140,
            description="Hazelnut infusion with whipped cream topping",
        ),
        regular_item(
            "double-choco-chip-frappe",
            "Double Choco Chip Frappe",
            "cold-coffees",
            140,
            description="Chocolaty sibling of chocolate heaven pleasure",
        ),
    ]

    # --- MILK SHAKES & SMOOTHIES ---
    shakes = [
        ("frozen-strawberry-margarita", "Frozen Strawberry Margarita Delight", 110),
        ("chocolate-heaven-pleasure", "Chocolate Heaven Pleasure", 130),
        ("toasted-marsh-mallow", "Toasted Marsh Mallow", 130),
        ("cadbury-gems-kitkat", "Cadbury Gems Meets Kit-Kat", 130),
        ("no-cardio-only-oreo", "No Cardio Only Oreo", 130),
        ("strawberry-toasted-marsh-mallow", "Strawberry Toasted Marsh Mallow", 130),
        ("nutella-love-story", "Nutella Love Story", 150),
        ("choco-lava-shake", "Choco Lava Shake", 170),
        ("biscoff-shake", "Biscoff Shake", 170),
        ("ferrero-rocher-shake", "Ferrero Rocher Shake", 180),
    ]
    for item_id, name, price in shakes:
        items.append(regular_item(item_id, name, "milkshakes-smoothies", price))

    # --- HAND TOASTED VEG PIZZAS ---
    items += [
        pizza_item(
            "margherita",
            "Margherita",
            "veg-pizzas",
            (150, 320, 530),
            description="An old country original — classic cheese",
        ),
        pizza_item(
            "c4-margherita",
            "C4 Margherita",
            "veg-pizzas",
            (200, 390, 590),
            description="Extra cheese on cheese — double cheese",
        ),
        pizza_item(
            "three-dimensions",
            "3 Dimensions",
            "veg-pizzas",
            (220, 380, 610),
            description="OTC / OTS / OTM — onion, tomato, capsicum, sweet corn, mushroom",
        ),
        pizza_item(
            "high-five",
            "High-Five",
            "veg-pizzas",
            (230, 400, 630),
            description="Onion, capsicum, mushroom, tomato, red paprika",
        ),
        pizza_item(
            "paneer-king",
            "Paneer King",
            "veg-pizzas",
            (250, 450, 670),
            description="Onion, capsicum, paneer, tomato, red paprika",
        ),
        pizza_item(
            "exotica",
            "Exotica",
            "veg-pizzas",
            (250, 410, 650),
            description="Red paprika, baby corn, capsicum, olives, jalapeno",
        ),
        pizza_item(
            "spicy-paneer",
            "Spicy Paneer",
            "veg-pizzas",
            (260, 460, 680),
            description="Tandoori spicy paneer, onion, capsicum, tomato & red paprika",
        ),
        pizza_item(
            "paneer-makhni",
            "Paneer Makhni",
            "veg-pizzas",
            (260, 460, 680),
            description="Makhni sauce, makhni paneer, onion, capsicum, tomato",
        ),
        pizza_item(
            "pindi-paneer",
            "Pindi Paneer",
            "veg-pizzas",
            (260, 480, 720),
            description="Tandoori spicy paneer, onion, tomato, sweet corn, jalapeno",
        ),
        pizza_item(
            "veggie-blast",
            "Veggie Blast",
            "veg-pizzas",
            (280, 460, 660),
            description="Capsicum, olives, paneer, mushroom, onion, tomato, sweet corn",
        ),
    ]

    # --- HAND TOASTED NON-VEG PIZZAS ---
    items += [
        pizza_item(
            "chicken-tikka-pizza",
            "Chicken Tikka",
            "non-veg-pizzas",
            (260, 480, 700),
            description="Chicken tikka, onion, red paprika, tandoori sauce",
            veg=False,
        ),
        pizza_item(
            "chicken-pepperoni",
            "Chicken Pepperoni",
            "non-veg-pizzas",
            (270, 490, 690),
            description="Chicken pepperoni & cheese, red paprika, pizza sauce",
            veg=False,
        ),
        pizza_item(
            "pindi-chicken",
            "Pindi Chicken",
            "non-veg-pizzas",
            (270, 510, 710),
            description="BBQ chicken, onion, red paprika, sweet corn, jalapeno, olives",
            veg=False,
        ),
        pizza_item(
            "panama-chicken",
            "Panama Chicken",
            "non-veg-pizzas",
            (280, 500, 710),
            description="Chicken, capsicum, mushroom, red paprika, green olives",
            veg=False,
        ),
        pizza_item(
            "chicken-burst",
            "Chicken Burst",
            "non-veg-pizzas",
            (320, 570, 820),
            description="Chicken tikka, meatball, salami, spicy chicken, red paprika, onion",
            veg=False,
        ),
    ]

    modifiers = [
        # Pizza upgrades (large-tier pricing)
        {"id": "c4_cheesilicious", "name": "C4 Cheesilicious", "group": "pizza_upgrade", "price_cents": rupees(80), "is_86d": False},
        {"id": "zesty_c4", "name": "Zesty C4", "group": "pizza_upgrade", "price_cents": rupees(80), "is_86d": False},
        {"id": "cheese_burst", "name": "Cheese Burst", "group": "pizza_upgrade", "price_cents": rupees(310), "is_86d": False},
        {"id": "extra_cheese_pizza", "name": "Extra Cheese", "group": "pizza_upgrade", "price_cents": rupees(120), "is_86d": False},
        # Extra toppings (large-tier pricing)
        {"id": "onion", "name": "Onion", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "capsicum", "name": "Capsicum", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "sweet_corn", "name": "Sweet Corn", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "jalapeno", "name": "Jalapeno", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "red_paprika", "name": "Red Paprika", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "mushroom", "name": "Mushroom", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "baby_corn", "name": "Baby Corn", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "black_olives", "name": "Black Olives", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "extra_chicken", "name": "Extra Chicken", "group": "toppings", "price_cents": rupees(200), "is_86d": False},
        # Pasta / sides add-ons
        {"id": "pasta_chicken_addon", "name": "Add Chicken", "group": "pasta_addon", "price_cents": rupees(80), "is_86d": False},
        {"id": "peri_peri_masala", "name": "Peri-Peri Masala", "group": "sides_addon", "price_cents": rupees(10), "is_86d": False},
        {"id": "extra_thousand_dip", "name": "Extra Thousand Dip", "group": "sides_addon", "price_cents": rupees(10), "is_86d": False},
        {"id": "extra_cheese_slices", "name": "Extra Cheese Slices", "group": "burger_addon", "price_cents": rupees(30), "is_86d": False},
        # Legacy test-compatible toppings (fixture tests)
        {"id": "pepperoni", "name": "Pepperoni", "group": "toppings", "price_cents": rupees(40), "is_86d": False},
        {"id": "extra_cheese", "name": "Extra Cheese Topping", "group": "toppings", "price_cents": rupees(60), "is_86d": False},
        {"id": "anchovies", "name": "Anchovies", "group": "toppings", "price_cents": rupees(40), "is_86d": True},
    ]

    return {
        "restaurant": {"name": BRAND, "currency": "INR", "tagline": "Make It A Habit To Eat"},
        "sizes": [
            {"id": "regular", "name": "Regular"},
            {"id": "small", "name": "Small (S)"},
            {"id": "medium", "name": "Medium (M)"},
            {"id": "large", "name": "Large (L)"},
        ],
        "categories": [
            {"id": "veg-pizzas", "name": "Hand Toasted Veg Pizzas"},
            {"id": "non-veg-pizzas", "name": "Hand Toasted Non-Veg Pizzas"},
            {"id": "mojito-vohito", "name": "Mojito - Vohito"},
            {"id": "iced-teas", "name": "Iced Teas"},
            {"id": "sides", "name": "Sides"},
            {"id": "pastas", "name": "Pastas"},
            {"id": "crispy-toasties", "name": "Crispy Toasties"},
            {"id": "subs", "name": "Subs"},
            {"id": "burgers", "name": "Burgers"},
            {"id": "wraps", "name": "Wraps"},
            {"id": "desserts", "name": "Desserts"},
            {"id": "coffees", "name": "Coffees"},
            {"id": "hot-beverages", "name": "Hot Beverages"},
            {"id": "cold-coffees", "name": "Cold Coffees"},
            {"id": "milkshakes-smoothies", "name": "Milk Shakes & Smoothies"},
        ],
        "items": items,
        "modifiers": modifiers,
        "rules": {
            "half_and_half": {
                "requires_both_sides": True,
                "max_toppings_per_side": 5,
                "extra_cheese_side_specific": True,
            },
            "max_whole_toppings": 8,
        },
    }


if __name__ == "__main__":
    menu = build_menu()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(menu, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(menu['items'])} items to {OUT}")
