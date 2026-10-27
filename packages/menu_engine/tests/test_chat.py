"""Tests for Groq text chat agent (keyword fallback — no API key required)."""

from menu_engine.chat.groq_agent import GroqChatAgent
from menu_engine.menu.loader import load_menu
from menu_engine.tools.order_tools import create_order_tools
from menu_engine.db.repository import CartRepository
from menu_engine.db.models import create_db_engine, init_db
from sqlalchemy.orm import sessionmaker


def _make_agent(session_id: str = "chat-test") -> GroqChatAgent:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    repo = CartRepository(sessionmaker(bind=engine, expire_on_commit=False))
    tools = create_order_tools(
        load_menu(),
        session_id,
        repository=repo,
    )
    return GroqChatAgent(tools, repo, session_id, api_key="")


def test_keyword_add_margherita_pizza():
    agent = _make_agent("chat-add")
    out = agent.chat("I'd like a medium margherita pizza")
    assert out["mode"] == "keyword"
    assert out["tool_result"]["success"] is True
    assert "Added" in out["reply"]


def test_keyword_read_back_empty():
    agent = _make_agent("chat-readback")
    out = agent.chat("read back my order")
    assert out["mode"] == "keyword"
    assert "empty" in out["reply"].lower()


def test_keyword_unknown_prompts_help():
    agent = _make_agent("chat-help")
    out = agent.chat("hello there")
    assert out["mode"] == "keyword"
    assert "GROQ_API_KEY" in out["reply"] or "order" in out["reply"].lower() or "DIALOG" in out["reply"]
