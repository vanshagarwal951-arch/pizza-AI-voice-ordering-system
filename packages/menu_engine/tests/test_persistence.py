import pytest
from sqlalchemy.orm import sessionmaker

from menu_engine.cart.persistent import PersistentSessionManager
from menu_engine.db.models import create_db_engine, init_db
from menu_engine.db.repository import CartRepository, reset_cart_repository
from menu_engine.menu.loader import load_menu_from_path
from menu_engine.tools.order_tools import create_order_tools
from menu_engine.types import ToppingSelection, AddItemInput
from tests.conftest import FIXTURE_MENU_PATH


@pytest.fixture
def repo():
    reset_cart_repository()
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return CartRepository(sessionmaker(bind=engine, expire_on_commit=False))


@pytest.fixture
def menu():
    return load_menu_from_path(FIXTURE_MENU_PATH)


def test_cart_persists_across_reload(repo, menu):
    session_id = "test-session-persist"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)

    result = tools.add_item(
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection("pepperoni")],
        )
    )
    assert result.success

    # Simulate new process loading from DB
    mgr2 = PersistentSessionManager(repo)
    tools2 = create_order_tools(menu, session_id, session_manager=mgr2, repository=repo)
    readback = tools2.read_back_cart()
    assert readback.cart_summary.item_count == 1
    assert readback.cart_summary.total_cents == 1649


def test_finalize_order_creates_record(repo, menu):
    session_id = "test-session-finalize"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)

    tools.add_item(
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="small",
            whole_toppings=[ToppingSelection("mushroom")],
        )
    )
    finalize = tools.finalize_order()
    assert finalize.success
    assert "Order confirmed" in finalize.message

    orders = repo.list_orders()
    assert len(orders) == 1
    assert orders[0]["session_id"] == session_id

    # Session is finalized — cannot add until restarted
    result = tools.add_item(
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="small",
            whole_toppings=[ToppingSelection("pepperoni")],
        )
    )
    assert not result.success

    repo.restart_session(session_id)
    mgr3 = PersistentSessionManager(repo)
    tools3 = create_order_tools(menu, session_id, session_manager=mgr3, repository=repo)
    retry = tools3.add_item(
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="small",
            whole_toppings=[ToppingSelection("pepperoni")],
        )
    )
    assert retry.success


def test_list_active_sessions(repo, menu):
    session_id = "active-room-1"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)
    tools.add_item(
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="large",
            whole_toppings=[ToppingSelection("pepperoni")],
        )
    )

    sessions = repo.list_active_sessions()
    assert any(s["id"] == session_id for s in sessions)


def test_checkout_details_used_on_finalize(repo, menu):
    session_id = "checkout-session"
    mgr = PersistentSessionManager(repo)
    tools = create_order_tools(menu, session_id, session_manager=mgr, repository=repo)

    repo.set_checkout_details(
        session_id, payment_method="upi", customer_phone="+919876543210"
    )
    tools.add_item(
        AddItemInput(
            menu_item_id="build-your-own",
            size_id="small",
            whole_toppings=[ToppingSelection("pepperoni")],
        )
    )
    result = tools.finalize_order()
    assert result.success
    assert "UPI" in result.message or "upi" in result.message.lower()
    assert "9876543210" in result.message

    orders = repo.list_orders()
    assert orders[0]["payment_method"] == "upi"
