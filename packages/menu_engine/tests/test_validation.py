import pytest

from menu_engine.cart.cart import Cart
from menu_engine.menu.loader import load_menu_from_path
from menu_engine.tools.order_tools import create_order_tools
from menu_engine.types import AddItemInput, ToppingSelection
from menu_engine.validation.validator import validate_add_item, validate_remove_item
from tests.conftest import FIXTURE_MENU_PATH


@pytest.fixture
def menu():
    return load_menu_from_path(FIXTURE_MENU_PATH)


def test_t1_simple_large_pepperoni(menu):
    ok, order, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection("pepperoni")],
        ),
    )
    assert ok and order and not error
    assert order.line_total_cents == 1649


def test_t2_rejects_86d_topping(menu):
    ok, _, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection("anchovies")],
        ),
    )
    assert not ok and error
    assert error.code == "R03"
    assert "86'd" in error.message


def test_t3_rejects_invalid_size(menu):
    ok, _, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="personal-pizza",
            size_id="large",
            whole_toppings=[ToppingSelection("pepperoni")],
        ),
    )
    assert not ok and error
    assert error.code == "R02"


def test_t4_half_pepperoni_half_mushroom(menu):
    ok, order, _ = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            is_half_and_half=True,
            left_toppings=[ToppingSelection("pepperoni")],
            right_toppings=[ToppingSelection("mushroom")],
        ),
    )
    assert ok and order
    assert order.is_half_and_half
    assert len(order.left_toppings) == 1
    assert len(order.right_toppings) == 1
    assert order.line_total_cents == 1774


def test_t5_extra_cheese_on_pepperoni_side_only(menu):
    ok, order, _ = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            is_half_and_half=True,
            left_toppings=[
                ToppingSelection("pepperoni"),
                ToppingSelection("extra_cheese", extra=True),
            ],
            right_toppings=[ToppingSelection("mushroom")],
        ),
    )
    assert ok and order
    extra = next(t for t in order.left_toppings if t.modifier_id == "extra_cheese")
    assert extra.extra is True
    assert not any(t.modifier_id == "extra_cheese" for t in order.right_toppings)
    assert order.line_total_cents == 2037


def test_t6_half_and_half_missing_right_side(menu):
    ok, _, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            is_half_and_half=True,
            left_toppings=[ToppingSelection("pepperoni")],
        ),
    )
    assert not ok and error
    assert error.code == "R05"


def test_t7_max_toppings_per_side(menu):
    six = [
        ToppingSelection("pepperoni"),
        ToppingSelection("mushroom"),
        ToppingSelection("sausage"),
        ToppingSelection("onion"),
        ToppingSelection("green_pepper"),
        ToppingSelection("extra_cheese"),
    ]
    ok, _, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            is_half_and_half=True,
            left_toppings=six,
            right_toppings=[ToppingSelection("mushroom")],
        ),
    )
    assert not ok and error
    assert error.code == "R06"


def test_t8_duplicate_topping(menu):
    ok, _, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            is_half_and_half=True,
            left_toppings=[
                ToppingSelection("pepperoni"),
                ToppingSelection("pepperoni"),
            ],
            right_toppings=[ToppingSelection("mushroom")],
        ),
    )
    assert not ok and error
    assert error.code == "R08"


def test_t9_remove_by_cart_id(menu):
    cart = Cart()
    ok, order, _ = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection("pepperoni")],
        ),
    )
    assert ok and order
    line = cart.add(order)
    assert not cart.is_empty()
    cart.remove(line.id)
    assert cart.is_empty()


def test_t10_remove_nonexistent_id():
    error = validate_remove_item("non-existent-id", [])
    assert error and error.code == "R10"


def test_t11_read_back_two_items(menu):
    tools = create_order_tools(menu, "test-session-11")
    tools.add_item(
        {
            "menu_item_id": "build-your-own",
            "size_id": "large",
            "whole_toppings": [{"modifier_id": "pepperoni"}],
        }
    )
    tools.add_item(
        {
            "menu_item_id": "build-your-own",
            "size_id": "small",
            "whole_toppings": [{"modifier_id": "mushroom"}],
        }
    )
    result = tools.read_back_cart()
    assert result.success
    assert result.cart_summary.item_count == 2
    assert result.cart_summary.total_cents == 1649 + 1124
    assert "Total:" in result.message


def test_t12_nine_whole_toppings(menu):
    ids = [
        "pepperoni", "mushroom", "sausage", "onion", "green_pepper",
        "extra_cheese", "pepperoni", "mushroom", "sausage",
    ]
    ok, _, error = validate_add_item(
        menu,
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection(i) for i in ids],
        ),
    )
    assert not ok and error
    assert error.code == "R06"
