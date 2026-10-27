from __future__ import annotations

import json
import logging
from typing import Any

from menu_engine import create_order_tools, get_cart_repository, load_menu
from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.db.repository import (
    ConcurrentUpdateError,
    IdempotencyConflictError,
    OrderIntegrityError,
)
from menu_engine.tools.order_tools import execute_tool, tool_result_to_voice_dict
from menu_engine.types import ToolResult

logger = logging.getLogger(__name__)


class SessionToolExecutor:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._menu = load_menu()
        self._repo = get_cart_repository()
        self._repo.restart_session(session_id)
        mgr = PersistentSessionManager(self._repo)
        self._tools = create_order_tools(
            self._menu, session_id, session_manager=mgr, repository=self._repo
        )
        self._repo.start_call_log(session_id, room_name=session_id)

    def run(self, name: str, args: dict[str, Any]) -> str:
        try:
            self._repo.append_transcript(
                self._session_id, "tool", f"{name}({json.dumps(args)})"
            )
            result = execute_tool(self._tools, name, args)
            self._repo.append_transcript(
                self._session_id, "tool_result", result.message
            )
            return json.dumps(tool_result_to_voice_dict(result))
        except ConcurrentUpdateError:
            msg = "The order was updated concurrently in another tab or request. Please review your cart and retry."
            return json.dumps(
                tool_result_to_voice_dict(
                    ToolResult(success=False, message=msg, error_code="R10")
                )
            )
        except IdempotencyConflictError as exc:
            return json.dumps(
                tool_result_to_voice_dict(
                    ToolResult(success=False, message=str(exc), error_code="R10")
                )
            )
        except OrderIntegrityError as exc:
            logger.error("Order persistence failed for session %s: %s", self._session_id, exc)
            return json.dumps(
                tool_result_to_voice_dict(
                    ToolResult(
                        success=False,
                        message="Your order could not be saved to our database. No charge was made and no order was placed.",
                        error_code="R01",
                    )
                )
            )
        except ValueError as exc:
            message = str(exc)
            if "not active" in message.lower():
                message = (
                    "This ordering session has ended. Please disconnect and "
                    "click Connect Microphone to start a new order."
                )
            return json.dumps(
                tool_result_to_voice_dict(
                    ToolResult(success=False, message=message, error_code="R10")
                )
            )
        except Exception as exc:
            logger.error("Unexpected tool execution error: %s", exc, exc_info=True)
            return json.dumps(
                tool_result_to_voice_dict(
                    ToolResult(
                        success=False,
                        message="Sorry, something went wrong processing your request. Please try again.",
                        error_code="R01",
                    )
                )
            )
