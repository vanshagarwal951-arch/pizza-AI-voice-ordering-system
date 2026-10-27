from menu_engine.pricing import calculate_line_total, calculate_topping_price, format_spoken_amount
from menu_engine.types import AddItemInput, ToppingSelection
from menu_engine.validation.validator import validate_add_item
from menu_engine.menu.loader import load_menu_from_path
from tests.conftest import FIXTURE_MENU_PATH


def test_p1_base_plus_two_toppings():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    ok, order, _ = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection("pepperoni"), ToppingSelection("mushroom")],
        ),
    )
    assert ok and order
    assert order.line_total_cents == 1774


def test_p2_extra_cheese_pricing():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    price = calculate_topping_price(menu, [ToppingSelection("extra_cheese", extra=True)])
    assert price == 263


def test_p3_half_and_half_priced_per_side():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    total = calculate_line_total(
        menu,
        menu_item_id="build-your-own",
        size_id="large",
        is_half_and_half=True,
        left_toppings=[
            ToppingSelection("pepperoni"),
            ToppingSelection("extra_cheese", extra=True),
        ],
        right_toppings=[ToppingSelection("mushroom")],
        whole_toppings=[],
    )
    assert total == 2037


def test_spoken_inr_seven_hundred():
    assert format_spoken_amount(70000, "INR") == "seven hundred rupees"


def test_spoken_inr_with_paise():
    assert format_spoken_amount(70150, "INR") == "seven hundred one rupees and fifty paise"


def test_spoken_usd():
    assert format_spoken_amount(999, "USD") == "nine dollars and ninety nine cents"
