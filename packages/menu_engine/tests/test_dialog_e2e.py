"""Production DIALOG menu order flow tests."""

from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.db.models import create_db_engine, init_db
from menu_engine.db.repository import CartRepository, reset_cart_repository
from menu_engine.menu.loader import load_menu
from menu_engine.tools.order_tools import create_order_tools
from menu_engine.types import AddItemInput
from sqlalchemy.orm import sessionmaker


def test_dialog_menu_finalize_with_inr():
    reset_cart_repository()
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    repo = CartRepository(sessionmaker(bind=engine, expire_on_commit=False))
    menu = load_menu()
    session_id = "dialog-finalize-inr"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)

    assert tools.add_item(
        AddItemInput(menu_item_id="margherita", size_id="medium")
    ).success
    assert tools.add_item(
        AddItemInput(menu_item_id="cafe-latte", size_id="regular")
    ).success

    finalize = tools.finalize_order()
    assert finalize.success, finalize.message
    assert "Order confirmed" in finalize.message
    assert repo.list_orders()[0]["session_id"] == session_id
