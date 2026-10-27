"""Groq-powered text chat with the same order tools as the voice agent."""

from __future__ import annotations

import json
import os
from typing import Any

from menu_engine.utils.groq_client import get_groq_model, groq_chat_completion

from menu_engine.db.repository import CartRepository
from menu_engine.prompts.system import SYSTEM_PROMPT
from menu_engine.tools.order_tools import OrderTools, execute_tool, tool_result_to_dict

TOPPING_IDS_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Topping modifier IDs, e.g. pepperoni, mushroom, extra_cheese",
}

ORDER_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "Add a validated menu item to the cart.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Menu item name as the customer says it, e.g. Margherita, Chicken Tikka Pizza",
                    },
                    "size": {
                        "type": "string",
                        "description": "Size: regular for most items, or small/medium/large for pizzas",
                        "default": "regular",
                    },
                    "is_half_and_half": {"type": "boolean", "default": False},
                    "left_toppings": TOPPING_IDS_SCHEMA,
                    "right_toppings": TOPPING_IDS_SCHEMA,
                    "whole_toppings": TOPPING_IDS_SCHEMA,
                    "crust_id": {"type": "string"},
                    "quantity": {"type": "integer", "minimum": 1, "default": 1},
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item",
            "description": "Remove a line item from the cart by cart_item_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cart_item_id": {"type": "string"},
                },
                "required": ["cart_item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_back_cart",
            "description": "Read back the current cart contents and total.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_order",
            "description": (
                "Submit the order to the kitchen after customer confirmation. "
                "Ask payment method (cod/upi/razorpay) and phone number for SMS before calling."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "payment_method": {
                        "type": "string",
                        "enum": ["cod", "upi", "razorpay"],
                        "description": "How the customer will pay",
                    },
                    "customer_phone": {
                        "type": "string",
                        "description": "Customer mobile for SMS confirmation, e.g. +919876543210",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Must be true only if customer explicitly confirmed the complete cart and total price",
                    },
                    "idempotency_key": {
                        "type": "string",
                        "description": "Optional unique key to ensure idempotent order submission",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_to_human",
            "description": "Transfer the customer to a human staff member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
            },
        },
    },
]

MAX_TOOL_ROUNDS = 6


class GroqChatAgent:
    def __init__(
        self,
        tools: OrderTools,
        repository: CartRepository,
        session_id: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._tools = tools
        self._repository = repository
        self._session_id = session_id
        self._api_key = (
            api_key if api_key is not None else os.getenv("GROQ_API_KEY", "")
        ).strip()
        self._model = model or get_groq_model()
        self._history = repository.get_chat_history(session_id)

    @property
    def uses_groq(self) -> bool:
        return bool(self._api_key)

    def chat(self, user_message: str) -> dict[str, Any]:
        self._repository.start_call_log(self._session_id, room_name=self._session_id)
        self._repository.append_transcript(self._session_id, "user", user_message)
        self._history.append({"role": "user", "content": user_message})

        if not self._api_key:
            reply, tool_results = _keyword_fallback(self._tools, user_message)
            self._repository.append_transcript(self._session_id, "assistant", reply)
            self._history.append({"role": "assistant", "content": reply})
            return _build_response(reply, tool_results, mode="keyword")

        try:
            reply, tool_results = self._run_groq_loop()
        except Exception as exc:  # noqa: BLE001
            # Don't expose internal error details to client
            reply = (
                "I'm having trouble reaching the AI service right now. "
                "You can still use the Quick Tool Test buttons on the Live Order tab."
            )
            tool_results = []
            # Log the actual error server-side for debugging
            import logging
            logging.error(f"Groq chat error for session {self._session_id}: {exc}")
            mode = "error"
        else:
            mode = "groq"

        self._repository.append_transcript(self._session_id, "assistant", reply)
        self._history.append({"role": "assistant", "content": reply})
        return _build_response(reply, tool_results, mode=mode)

    def _run_groq_loop(self) -> tuple[str, list[dict[str, Any]]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self._history,
        ]
        tool_results: list[dict[str, Any]] = []

        for _ in range(MAX_TOOL_ROUNDS):
            response = _groq_chat_completion(
                api_key=self._api_key,
                model=self._model,
                messages=messages,
                tools=ORDER_TOOL_DEFINITIONS,
            )
            choice = response["choices"][0]["message"]
            tool_calls = choice.get("tool_calls") or []

            if not tool_calls:
                content = (choice.get("content") or "").strip()
                if not content:
                    content = "How can I help with your order?"
                return content, tool_results

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.get("content"),
                    "tool_calls": tool_calls,
                }
            )

            for call in tool_calls:
                fn = call["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}

                self._repository.append_transcript(
                    self._session_id, "tool", f"{name}({json.dumps(args)})"
                )
                result = execute_tool(self._tools, name, args)
                payload = tool_result_to_dict(result)
                tool_results.append({"tool": name, "args": args, "result": payload})
                self._repository.append_transcript(
                    self._session_id, "tool_result", result.message
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(payload),
                    }
                )

        return (
            "I need a moment — could you repeat what you'd like to order?",
            tool_results,
        )


def _groq_chat_completion(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        return groq_chat_completion(
            api_key=api_key,
            model=model,
            messages=messages,
            tools=tools,
            temperature=0.4,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Groq API error: {exc}") from exc


def _build_response(
    reply: str, tool_results: list[dict[str, Any]], *, mode: str
) -> dict[str, Any]:
    data: dict[str, Any] = {"reply": reply, "mode": mode}
    if tool_results:
        data["tool_results"] = tool_results
        data["tool_result"] = tool_results[-1]["result"]
    return data


def _keyword_fallback(tools: OrderTools, text: str) -> tuple[str, list[dict[str, Any]]]:
    """Offline demo parser when GROQ_API_KEY is not set."""
    lowered = text.lower().strip()
    tool_results: list[dict[str, Any]] = []

    if any(w in lowered for w in ("read back", "readback", "what's my order", "my cart")):
        result = tools.read_back_cart()
    elif any(w in lowered for w in ("finalize", "confirm", "submit", "place order", "checkout")):
        result = tools.finalize_order()
    elif any(w in lowered for w in ("remove", "delete")):
        summary = tools.read_back_cart()
        return (
            "Use remove_item with a cart_item_id from your cart. "
            "Try: 'read back my order' to see line IDs in the dashboard.",
            [{"tool": "read_back_cart", "args": {}, "result": tool_result_to_dict(summary)}],
        )
    elif "half" in lowered and ("pepperoni" in lowered or "mushroom" in lowered):
        size = "large" if "large" in lowered else "medium" if "medium" in lowered else "small"
        toppings = []
        if "pepperoni" in lowered:
            toppings.append({"modifier_id": "pepperoni"})
        if "mushroom" in lowered:
            toppings.append({"modifier_id": "mushroom"})
        args = {
            "item_name": "Build Your Own Pizza",
            "size": size,
            "whole_toppings": toppings or [{"modifier_id": "pepperoni"}],
        }
        result = tools.add_item(args)
        tool_results.append({"tool": "add_item", "args": args, "result": tool_result_to_dict(result)})
        return result.message, tool_results
    elif any(w in lowered for w in ("pepperoni", "mushroom", "pizza", "margherita")):
        size = "large" if "large" in lowered else "medium" if "medium" in lowered else "small"
        toppings = []
        if "pepperoni" in lowered:
            toppings.append({"modifier_id": "pepperoni"})
        if "mushroom" in lowered:
            toppings.append({"modifier_id": "mushroom"})
        args = {
            "item_name": "Margherita" if "margherita" in lowered else "Chicken Pepperoni",
            "size": size,
            "whole_toppings": toppings,
        }
        result = tools.add_item(args)
        tool_results.append({"tool": "add_item", "args": args, "result": tool_result_to_dict(result)})
        return result.message, tool_results
    elif any(w in lowered for w in ("burger", "latte", "mojito", "fries", "wrap", "sub")):
        item_map = {
            "burger": ("Crispy Chicken Burger", "regular"),
            "latte": ("Cafe Latte", "regular"),
            "mojito": ("Virgin Mint Mojito", "regular"),
            "fries": ("French Fries", "regular"),
            "wrap": ("Chicken Tikka Wrap", "regular"),
            "sub": ("Chicken Tikka Sub", "regular"),
        }
        for key, (item_name, size) in item_map.items():
            if key in lowered:
                args = {"item_name": item_name, "size": size}
                result = tools.add_item(args)
                tool_results.append({"tool": "add_item", "args": args, "result": tool_result_to_dict(result)})
                return result.message, tool_results
    else:
        return (
            "Welcome to DIALOG Pizza! Try: 'medium margherita pizza', 'chicken tikka wrap', "
            "'cafe latte', 'read back my order', or 'finalize order'. "
            "Set GROQ_API_KEY in .env for full AI chat.",
            [],
        )

    payload = tool_result_to_dict(result)
    tool_results.append({"tool": "inline", "args": {}, "result": payload})
    return result.message, tool_results
