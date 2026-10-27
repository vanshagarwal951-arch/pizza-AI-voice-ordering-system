from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.menu.loader import load_menu_from_path, resolve_item, resolve_size
from menu_engine.tools.order_tools import create_order_tools
from tests.conftest import FIXTURE_MENU_PATH


def test_resolve_item_by_name():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    item = resolve_item(menu, "Build Your Own Pizza")
    assert item is not None
    assert item["id"] == "build-your-own"


def test_resolve_item_partial_name():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    item = resolve_item(menu, "personal pizza")
    assert item is not None
    assert item["id"] == "personal-pizza"


def test_add_item_by_name():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-name-order")
    result = tools.add_item(
        {
            "item_name": "Build Your Own Pizza",
            "size": "large",
            "whole_toppings": [{"modifier_id": "pepperoni"}],
        }
    )
    assert result.success is True
    assert "Build Your Own Pizza" in result.message


def test_unavailable_item_message():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    for item in menu["items"]:
        if item["id"] == "personal-pizza":
            item["is_available"] = False
            break
    tools = create_order_tools(menu, "test-session-unavailable")
    result = tools.add_item({"item_name": "Personal Pizza", "size": "small"})
    assert result.success is False
    assert result.message == "This item is not available please order something else"


def test_finalize_includes_full_readback():
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    tools = create_order_tools(menu, "test-session-finalize-readback")
    tools.add_item(
        {
            "item_name": "Build Your Own Pizza",
            "size": "large",
            "whole_toppings": [{"modifier_id": "pepperoni"}],
        }
    )
    readback = tools.read_back_cart()
    assert "Build Your Own Pizza" in readback.message
    assert "Total:" in readback.message


def test_restart_session_after_finalize():
    from menu_engine.db.models import create_db_engine, init_db
    from menu_engine.db.repository import CartRepository, reset_cart_repository
    from sqlalchemy.orm import sessionmaker

    reset_cart_repository()
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    repo = CartRepository(sessionmaker(bind=engine, expire_on_commit=False))
    menu = load_menu_from_path(FIXTURE_MENU_PATH)
    session_id = "restart-room"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
    tools.add_item({"item_name": "Build Your Own Pizza", "size": "large"})
    assert tools.finalize_order().success

    restarted = repo.restart_session(session_id)
    assert restarted["restarted"] is True

    mgr2 = PersistentSessionManager(repo)
    tools2 = create_order_tools(menu, session_id, session_manager=mgr2, repository=repo)
    result = tools2.add_item({"item_name": "Build Your Own Pizza", "size": "medium"})
    assert result.success
    assert tools2.read_back_cart().cart_summary.item_count == 1
