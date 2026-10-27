"""Groq/OpenAI strict tool schemas must not use nested object arrays."""

from __future__ import annotations

from menu_engine.chat.groq_agent import ORDER_TOOL_DEFINITIONS


def _add_item_params() -> dict:
    for tool in ORDER_TOOL_DEFINITIONS:
        if tool["function"]["name"] == "add_item":
            return tool["function"]["parameters"]
    raise AssertionError("add_item tool not found")


def test_groq_add_item_uses_string_topping_arrays():
    params = _add_item_params()
    for field in ("whole_toppings", "left_toppings", "right_toppings"):
        items = params["properties"][field]["items"]
        assert items == {"type": "string"}, f"{field} must be array of strings for Groq strict mode"
    assert params.get("additionalProperties") is False
