from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from menu_engine.cart.cart import Cart, SessionManager, default_session_manager
from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.db.repository import (
    CartRepository,
    ConcurrentUpdateError,
    IdempotencyConflictError,
    OrderIntegrityError,
)
from menu_engine.menu.loader import (
    default_size_for_item,
    format_toppings,
    resolve_item,
    resolve_size,
)
from menu_engine.pricing import format_cents, format_spoken_amount
from menu_engine.types import AddItemInput, CartSummary, MenuData, ToolResult, ToppingSelection
from menu_engine.validation.validator import validate_add_item, validate_remove_item

ALLOWED_TOOLS = frozenset({
    "add_item",
    "remove_item",
    "read_back_cart",
    "finalize_order",
    "transfer_to_human",
})


@dataclass
class OrderTools:
    _menu: MenuData
    _cart: Cart
    _session_id: str
    _session_manager: SessionManager
    _repository: CartRepository | None = None

    def _persist(self) -> None:
        if isinstance(self._session_manager, PersistentSessionManager):
            try:
                self._session_manager.persist(self._session_id)
            except ConcurrentUpdateError:
                # Reload to keep local memory synchronized with latest state
                self._session_manager.reload(self._session_id)
                raise

    def _ensure_active(self) -> ToolResult | None:
        if self._repository is None:
            return None
        try:
            self._repository.ensure_session(self._session_id)
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc), error_code="R10")
        return None

    def add_item(self, input: AddItemInput | dict[str, Any]) -> ToolResult:
        blocked = self._ensure_active()
        if blocked:
            return blocked
        try:
            if isinstance(input, dict):
                input = _parse_add_item(self._menu, input)
            elif isinstance(input, AddItemInput):
                if input.quantity < 1 or input.quantity > 50:
                    return ToolResult(
                        success=False,
                        message="Quantity must be between 1 and 50.",
                        error_code="R03",
                    )
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc), error_code="R02")

        ok, order, error = validate_add_item(self._menu, input)
        if not ok or order is None:
            assert error
            return ToolResult(success=False, message=error.message, error_code=error.code)
        line = self._cart.add(order)
        try:
            self._persist()
        except ConcurrentUpdateError:
            return ToolResult(
                success=False,
                message="The cart was updated concurrently. Please review your cart and retry.",
                error_code="R10",
            )
        msg = _build_success_message(self._menu, order)
        return ToolResult(success=True, message=msg, cart_item_id=line.id)

    def remove_item(self, cart_item_id: str) -> ToolResult:
        blocked = self._ensure_active()
        if blocked:
            return blocked
        if not cart_item_id or not isinstance(cart_item_id, str):
            return ToolResult(
                success=False, message="Valid cart_item_id is required.", error_code="R02"
            )
        error = validate_remove_item(cart_item_id, self._cart.get_item_ids())
        if error:
            return ToolResult(success=False, message=error.message, error_code=error.code)
        self._cart.remove(cart_item_id)
        try:
            self._persist()
        except ConcurrentUpdateError:
            return ToolResult(
                success=False,
                message="The cart was updated concurrently. Please review your cart and retry.",
                error_code="R10",
            )
        return ToolResult(success=True, message="Removed that item from your cart.")

    def read_back_cart(self) -> ToolResult:
        summary = self._cart.summarize(self._menu)
        return ToolResult(success=True, message=summary.spoken_summary, cart_summary=summary)

    def finalize_order(
        self,
        *,
        payment_method: str | None = None,
        customer_phone: str | None = None,
        confirmed: bool = True,
        idempotency_key: str | None = None,
    ) -> ToolResult:
        if self._cart.is_empty():
            if self._repository is not None and idempotency_key:
                existing = self._repository.get_order_by_idempotency_key(idempotency_key)
                if existing:
                    pay_method = "cod"
                    try:
                        if existing.payments:
                            pay_method = existing.payments[0].method
                    except Exception:
                        pass
                    pay_label = {"cod": "cash on delivery", "upi": "UPI", "razorpay": "online payment"}.get(
                        pay_method, pay_method
                    )
                    msg = (
                        f"Order confirmed! {existing.spoken_summary} "
                        f"Order ID {existing.id[:8]}. Payment: {pay_label}."
                    )
                    return ToolResult(success=True, message=msg)
            return ToolResult(
                success=False,
                message="Your cart is empty — add something before finalizing.",
                error_code="R10",
            )
        if not confirmed:
            summary = self._cart.summarize(self._menu)
            total = format_spoken_amount(summary.total_cents, summary.currency)
            return ToolResult(
                success=False,
                message=(
                    f"Order requires explicit customer confirmation before finalizing. "
                    f"Cart contains {summary.item_count} items totaling {total}. "
                    "Please read back the cart and confirm with the customer."
                ),
                error_code="R10",
            )
        if self._repository is None:
            return ToolResult(
                success=False,
                message="Order persistence is not configured.",
                error_code="R01",
            )
        prefs = self._repository.get_checkout_details(self._session_id)
        pay_method = (payment_method or prefs.get("payment_method") or "cod").lower()
        phone = customer_phone if customer_phone is not None else prefs.get("customer_phone")
        if payment_method or customer_phone:
            self._repository.set_checkout_details(
                self._session_id,
                payment_method=pay_method,
                customer_phone=phone,
            )

        summary = self._cart.summarize(self._menu)
        try:
            order = self._repository.finalize_session(
                self._session_id,
                summary,
                self._menu,
                payment_method=pay_method,
                customer_phone=phone,
                idempotency_key=idempotency_key,
            )
        except IdempotencyConflictError as exc:
            return ToolResult(
                success=False,
                message=f"Order conflict: {exc}",
                error_code="R10",
            )
        except OrderIntegrityError as exc:
            return ToolResult(
                success=False,
                message=f"Order persistence failed: {exc}",
                error_code="R01",
            )
        except ConcurrentUpdateError:
            return ToolResult(
                success=False,
                message="Session was modified concurrently. Please review the cart and retry.",
                error_code="R10",
            )
        except ValueError as exc:
            return ToolResult(success=False, message=str(exc), error_code="R10")

        if isinstance(self._session_manager, PersistentSessionManager):
            self._session_manager.invalidate(self._session_id)
        total = format_spoken_amount(summary.total_cents, summary.currency)
        pay_label = {"cod": "cash on delivery", "upi": "UPI", "razorpay": "online payment"}.get(
            pay_method, pay_method
        )
        msg = (
            f"Order confirmed! {summary.spoken_summary} "
            f"Order ID {order.id[:8]}. Payment: {pay_label}."
        )
        if phone:
            msg += f" Confirmation SMS will be sent to {phone}."
        return ToolResult(
            success=True,
            message=msg,
            cart_summary=summary,
        )


def _parse_toppings(raw: Any) -> list[ToppingSelection]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("Toppings must be provided as a list.")
    if len(raw) > 20:
        raise ValueError("Too many toppings specified (maximum 20).")
    selections: list[ToppingSelection] = []
    for entry in raw:
        if isinstance(entry, str):
            clean = entry.strip()
            if clean:
                selections.append(ToppingSelection(modifier_id=clean[:50], extra=False))
        elif isinstance(entry, dict):
            mod_id = entry.get("modifier_id")
            if not mod_id or not isinstance(mod_id, str):
                continue
            selections.append(
                ToppingSelection(
                    modifier_id=str(mod_id).strip()[:50],
                    extra=bool(entry.get("extra", False)),
                )
            )
        else:
            raise ValueError("Invalid topping item format in selection list.")
    return selections


def _parse_add_item(menu: MenuData, data: dict[str, Any]) -> AddItemInput:
    item_query = data.get("item_name") or data.get("menu_item_id")
    if not item_query:
        raise ValueError("item_name is required")
    if not isinstance(item_query, str) or len(item_query.strip()) == 0:
        raise ValueError("item_name must be a non-empty string")
    if len(item_query) > 100:
        raise ValueError("item_name exceeds maximum length of 100 characters")

    resolved = resolve_item(menu, str(item_query))
    menu_item_id = resolved["id"] if resolved else str(item_query).strip()

    size_query = data.get("size") or data.get("size_id")
    if size_query:
        if not isinstance(size_query, str):
            raise ValueError("size must be a string")
        size_id = resolve_size(menu, menu_item_id, str(size_query)) or str(size_query).strip().lower()
    else:
        size_id = default_size_for_item(menu, menu_item_id) or "regular"

    qty_val = data.get("quantity", 1)
    try:
        qty = int(qty_val)
    except (ValueError, TypeError):
        raise ValueError("quantity must be a valid integer")
    if qty < 1 or qty > 50:
        raise ValueError("quantity must be between 1 and 50")

    return AddItemInput(
        menu_item_id=menu_item_id,
        size_id=size_id,
        is_half_and_half=bool(data.get("is_half_and_half", False)),
        left_toppings=_parse_toppings(data.get("left_toppings")),
        right_toppings=_parse_toppings(data.get("right_toppings")),
        whole_toppings=_parse_toppings(data.get("whole_toppings")),
        crust_id=str(data["crust_id"])[:50] if data.get("crust_id") else None,
        quantity=qty,
    )


def _build_success_message(menu: MenuData, order) -> str:
    currency = menu["restaurant"]["currency"]
    price = format_spoken_amount(order.line_total_cents, currency)
    msg = f"Added {order.size_name} {order.menu_item_name}"
    if order.is_half_and_half:
        left = format_toppings(menu, order.left_toppings)
        right = format_toppings(menu, order.right_toppings)
        msg += f": half {left} and half {right}"
    elif order.whole_toppings:
        msg += f" with {format_toppings(menu, order.whole_toppings)}"
    msg += f" to your cart. Item price: {price}."
    return msg


def create_order_tools(
    menu: MenuData,
    session_id: str,
    session_manager: SessionManager | None = None,
    repository: CartRepository | None = None,
) -> OrderTools:
    mgr = session_manager or default_session_manager
    cart = mgr.get_or_create(session_id)
    return OrderTools(
        _menu=menu,
        _cart=cart,
        _session_id=session_id,
        _session_manager=mgr,
        _repository=repository,
    )


def execute_tool(tools: OrderTools, name: str, args: dict[str, Any]) -> ToolResult:
    if not isinstance(name, str) or name not in ALLOWED_TOOLS:
        return ToolResult(
            success=False,
            message=f"Tool '{name}' is not permitted or unrecognized.",
            error_code="R01",
        )
    if not isinstance(args, dict):
        return ToolResult(
            success=False,
            message="Tool arguments must be a dictionary.",
            error_code="R02",
        )

    if name == "add_item":
        return tools.add_item(args)
    if name == "remove_item":
        cart_item_id = args.get("cart_item_id")
        if not cart_item_id or not isinstance(cart_item_id, str):
            return ToolResult(
                success=False,
                message="cart_item_id must be provided as a string.",
                error_code="R02",
            )
        return tools.remove_item(cart_item_id)
    if name == "read_back_cart":
        return tools.read_back_cart()
    if name == "finalize_order":
        confirmed = args.get("confirmed", True)
        return tools.finalize_order(
            payment_method=args.get("payment_method"),
            customer_phone=args.get("customer_phone"),
            confirmed=confirmed,
            idempotency_key=args.get("idempotency_key"),
        )
    if name == "transfer_to_human":
        return ToolResult(
            success=True,
            message=(
                "I'm connecting you with a team member now. "
                "Please hold — a staff member will be with you shortly."
            ),
        )
    return ToolResult(success=False, message=f"Unknown tool: {name}", error_code="R01")


def cart_summary_to_dict(summary: CartSummary) -> dict:
    return {
        "item_count": summary.item_count,
        "total_cents": summary.total_cents,
        "currency": summary.currency,
        "spoken_summary": summary.spoken_summary,
        "items": [
            {
                "id": item.id,
                "menu_item_name": item.menu_item_name,
                "size_name": item.size_name,
                "is_half_and_half": item.is_half_and_half,
                "line_total_cents": item.line_total_cents,
                "quantity": item.quantity,
            }
            for item in summary.items
        ],
    }


def tool_result_to_dict(result: ToolResult) -> dict:
    data = {
        "success": result.success,
        "message": result.message,
        "cart_item_id": result.cart_item_id,
        "error_code": result.error_code,
    }
    if result.cart_summary:
        data["cart_summary"] = cart_summary_to_dict(result.cart_summary)
    return data


def tool_result_to_voice_dict(result: ToolResult) -> dict:
    """Voice-safe tool payload — no raw cent fields for the LLM to misread."""
    return {
        "success": result.success,
        "message": result.message,
        "cart_item_id": result.cart_item_id,
        "error_code": result.error_code,
    }
