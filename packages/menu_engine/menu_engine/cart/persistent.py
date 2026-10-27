from __future__ import annotations

from menu_engine.cart.cart import Cart, SessionManager, default_session_manager
from menu_engine.db.repository import CartRepository


class PersistentSessionManager(SessionManager):
    """Loads and persists carts to the database with optimistic version tracking."""

    def __init__(self, repository: CartRepository) -> None:
        super().__init__()
        self._repository = repository
        self._versions: dict[str, int] = {}

    def get_or_create(self, session_id: str, reload: bool = False) -> Cart:
        if reload or session_id not in self._sessions:
            cart, version = self._repository.load_cart_with_version(session_id)
            self._sessions[session_id] = cart
            self._versions[session_id] = version
        return self._sessions[session_id]

    def get_version(self, session_id: str) -> int:
        if session_id not in self._versions:
            self.get_or_create(session_id)
        return self._versions.get(session_id, 1)

    def reload(self, session_id: str) -> Cart:
        return self.get_or_create(session_id, reload=True)

    def persist(self, session_id: str) -> int:
        cart = self.get_or_create(session_id)
        expected = self._versions.get(session_id)
        new_version = self._repository.save_cart(session_id, cart, expected_version=expected)
        self._versions[session_id] = new_version
        return new_version

    def invalidate(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._versions.pop(session_id, None)


def create_session_manager(repository: CartRepository | None = None) -> SessionManager:
    if repository is not None:
        return PersistentSessionManager(repository)
    return default_session_manager
