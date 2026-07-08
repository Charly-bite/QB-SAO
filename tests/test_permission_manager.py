"""
PermissionManager tests — covers load, has_permission, get_permissions,
get_all, set_permissions, and internal DB helpers.
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from core.permission_manager import (
    PermissionManager, DEFAULT_PERMISSIONS, PERMISSION_LABELS, TABLE_NAME,
)


class TestDefaults:
    """Verify defaults are seeded on construction."""

    def test_cache_seeded_with_all_roles(self):
        pm = PermissionManager()
        for role in DEFAULT_PERMISSIONS:
            assert role in pm._cache

    def test_admin_has_all_permissions(self):
        pm = PermissionManager()
        for key in PERMISSION_LABELS:
            assert key in pm._cache["admin"]


class TestLoadNoEngine:
    """load(None) logs a warning and keeps defaults."""

    def test_load_none_keeps_defaults(self):
        pm = PermissionManager()
        pm.load(None)
        assert pm._cache == {
            role: frozenset(perms)
            for role, perms in DEFAULT_PERMISSIONS.items()
        }


class TestLoadWithEngine:
    """load() with a working SQL engine."""

    def _mock_engine(self, rows):
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        conn.exec_driver_sql.return_value.fetchall.return_value = rows
        return engine

    def test_load_from_db_overrides_defaults(self):
        perms = ["nav.pedidos", "orders.edit"]
        engine = self._mock_engine([("operator", json.dumps(perms))])
        pm = PermissionManager()
        pm.load(engine)
        assert pm._cache["operator"] == frozenset(perms)

    def test_load_from_db_empty_table(self):
        engine = self._mock_engine([])
        pm = PermissionManager()
        pm.load(engine)
        # Should keep defaults when table is empty
        assert pm._cache["admin"] == frozenset(DEFAULT_PERMISSIONS["admin"])

    def test_load_db_exception_keeps_defaults(self):
        engine = MagicMock()
        engine.begin.side_effect = Exception("Connection failed")
        pm = PermissionManager()
        pm.load(engine)
        assert pm._cache["admin"] == frozenset(DEFAULT_PERMISSIONS["admin"])

    def test_load_bad_json_skips_role(self):
        engine = self._mock_engine([("operator", "NOT JSON")])
        pm = PermissionManager()
        pm.load(engine)
        # operator should keep its default since JSON parsing failed
        assert pm._cache["operator"] == frozenset(DEFAULT_PERMISSIONS["operator"])


class TestHasPermission:
    """has_permission() fast membership test."""

    def test_admin_has_permission(self):
        pm = PermissionManager()
        assert pm.has_permission("admin", "orders.edit") is True

    def test_seller_lacks_edit(self):
        pm = PermissionManager()
        assert pm.has_permission("seller", "orders.edit") is False

    def test_unknown_role_returns_false(self):
        pm = PermissionManager()
        assert pm.has_permission("nonexistent", "orders.edit") is False


class TestGetPermissions:
    """get_permissions() returns a mutable copy."""

    def test_returns_set(self):
        pm = PermissionManager()
        result = pm.get_permissions("viewer")
        assert isinstance(result, set)
        assert "orders.see_all" in result

    def test_unknown_role_returns_default_empty(self):
        pm = PermissionManager()
        result = pm.get_permissions("nonexistent_role")
        assert result == set()


class TestGetAll:
    """get_all() returns dict of all roles."""

    def test_returns_all_roles(self):
        pm = PermissionManager()
        result = pm.get_all()
        assert isinstance(result, dict)
        for role in DEFAULT_PERMISSIONS:
            assert role in result
            assert isinstance(result[role], set)


class TestSetPermissions:
    """set_permissions() persists and updates cache."""

    def test_set_without_engine_updates_cache(self):
        pm = PermissionManager()
        result = pm.set_permissions("viewer", ["nav.pedidos", "orders.see_all"])
        assert result is True
        assert pm._cache["viewer"] == frozenset({"nav.pedidos", "orders.see_all"})

    def test_set_filters_invalid_keys(self):
        pm = PermissionManager()
        pm.set_permissions("viewer", ["nav.pedidos", "invalid.key.here"])
        assert "invalid.key.here" not in pm._cache["viewer"]

    def test_set_with_engine_success(self):
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        pm = PermissionManager()
        pm._sql_engine = engine
        result = pm.set_permissions("viewer", ["nav.pedidos"])
        assert result is True
        assert pm._cache["viewer"] == frozenset({"nav.pedidos"})

    def test_set_with_engine_db_error_returns_false(self):
        engine = MagicMock()
        engine.begin.side_effect = Exception("DB error")
        pm = PermissionManager()
        pm._sql_engine = engine
        result = pm.set_permissions("viewer", ["nav.pedidos"])
        assert result is False

    def test_set_empty_permissions(self):
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        pm = PermissionManager()
        pm._sql_engine = engine
        result = pm.set_permissions("viewer", [])
        assert result is True
        assert pm._cache["viewer"] == frozenset()
