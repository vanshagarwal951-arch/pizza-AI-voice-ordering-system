from menu_engine.menu.loader import load_menu_from_path
from menu_engine.tools.order_tools import create_order_tools, tool_result_to_voice_dict
from tests.conftest import FIXTURE_MENU_PATH


def test_to1_add_item_result_shape():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-to1")
    result = tools.add_item(
        {
            "menu_item_id": "build-your-own",
            "size_id": "large",
            "whole_toppings": [{"modifier_id": "pepperoni"}],
        }
    )
    assert result.success is True
    assert isinstance(result.message, str)
    assert result.cart_item_id
    assert result.error_code is None


def test_to2_sequential_adds():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-to2")
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
    readback = tools.read_back_cart()
    assert readback.cart_summary.item_count == 2


def test_to4_string_topping_ids():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-to4")
    result = tools.add_item(
        {
            "menu_item_id": "build-your-own",
            "size_id": "large",
            "whole_toppings": ["pepperoni", "mushroom"],
        }
    )
    assert result.success is True
    assert "pepperoni" in result.message.lower() or "Pepperoni" in result.message


def test_to3_tool_only_interface():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-to3")
    assert hasattr(tools, "add_item")
    assert hasattr(tools, "remove_item")
    assert hasattr(tools, "read_back_cart")
    assert not hasattr(tools, "direct_add_to_cart")


def test_voice_tool_payload_omits_cents():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-voice-payload")
    tools.add_item(
        {
            "menu_item_id": "build-your-own",
            "size_id": "large",
            "whole_toppings": [{"modifier_id": "pepperoni"}],
        }
    )
    readback = tools.read_back_cart()
    payload = tool_result_to_voice_dict(readback)
    assert "cart_summary" not in payload
    assert "total_cents" not in str(payload)
    assert "rupees" in payload["message"].lower()
