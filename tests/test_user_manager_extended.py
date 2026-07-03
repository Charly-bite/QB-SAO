"""
Extended tests for core.user_manager — covers SQL persistence paths,
table creation, user loading, saving, and deletion from SQL.
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_um(sql_engine=None, users=None):
    """Create a UserManager with mocked SQL, pre-populated with optional users."""
    with patch("core.database_client.DatabaseClient") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.connect.return_value = bool(sql_engine)
        mock_instance.get_sql_engine.return_value = sql_engine
        mock_cls.return_value = mock_instance
        from core.user_manager import UserManager
        um = UserManager()

    if users:
        um.users = users
    return um


class TestEnsureTableExists:
    def test_no_engine(self):
        um = _make_um(sql_engine=None)
        um.sql_engine = None
        um._ensure_table_exists()  # Should not raise

    def test_with_engine_success(self):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        um = _make_um()
        um.sql_engine = mock_engine
        um._ensure_table_exists()
        assert mock_conn.exec_driver_sql.call_count == 3

    def test_with_engine_exception(self):
        mock_engine = MagicMock()
        mock_engine.begin.side_effect = Exception("SQL error")

        um = _make_um()
        um.sql_engine = mock_engine
        um._ensure_table_exists()  # Should not raise


class TestLoadUsers:
    def test_no_engine(self):
        um = _make_um()
        um.sql_engine = None
        um.users = {}
        um._load_users()
        assert um.users == {}

    def test_with_engine_success(self):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()

        # Simulate column names and a row
        mock_result.keys.return_value = [
            "username", "password_hash", "salt", "full_name", "email",
            "role", "is_active", "must_change_password", "last_login",
            "created_at", "warehouse",
        ]
        mock_result.fetchall.return_value = [
            ("testuser", "hash123", "salt456", "Test User", "test@test.com",
             "operator", True, False, "2026-01-01", "2026-01-01", "WH01"),
        ]
        mock_conn.exec_driver_sql.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        um = _make_um()
        um.sql_engine = mock_engine
        um.users = {}
        um._load_users()

        assert "testuser" in um.users
        assert um.users["testuser"]["role"] == "operator"
        assert um.users["testuser"]["full_name"] == "Test User"

    def test_with_engine_exception(self):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Load error")

        um = _make_um()
        um.sql_engine = mock_engine
        um.users = {}
        um._load_users()  # Should not raise
        assert um.users == {}


class TestSaveUserToSql:
    def test_no_engine(self):
        um = _make_um()
        um.sql_engine = None
        um._save_user_to_sql({"username": "x"})  # Should not raise

    def test_with_engine_success(self):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_raw = MagicMock()
        mock_cursor = MagicMock()
        mock_raw.cursor.return_value = mock_cursor
        mock_conn.connection = mock_raw
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        um = _make_um()
        um.sql_engine = mock_engine

        user_data = {
            "username": "testuser",
            "password_hash": "hash",
            "salt": "salt",
            "full_name": "Test",
            "email": "t@t.com",
            "role": "admin",
            "is_active": True,
            "must_change_password": False,
            "last_login": None,
            "created_at": "2026-01-01",
            "warehouse": "WH01",
        }
        um._save_user_to_sql(user_data)

        mock_cursor.execute.assert_called_once()
        mock_raw.commit.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_with_engine_exception(self):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Save error")

        um = _make_um()
        um.sql_engine = mock_engine
        um._save_user_to_sql({"username": "x"})  # Should not raise


class TestCreateDefaultAdmin:
    def test_creates_admin(self):
        um = _make_um()
        um.users = {}
        um._create_default_admin()
        assert "admin" in um.users
        assert um.users["admin"]["role"] == "admin"
        assert um.users["admin"]["password_hash"]  # Not empty


class TestDeleteUser:
    def test_delete_existing_with_sql(self):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_raw = MagicMock()
        mock_cursor = MagicMock()
        mock_raw.cursor.return_value = mock_cursor
        mock_conn.connection = mock_raw
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        um = _make_um()
        um.sql_engine = mock_engine
        um.users = {"testuser": {"username": "testuser"}, "admin": {"username": "admin"}}

        ok, msg = um.delete_user("testuser")
        assert ok is True
        assert "testuser" not in um.users
        mock_cursor.execute.assert_called()

    def test_delete_admin_blocked(self):
        um = _make_um()
        um.users = {"admin": {"username": "admin"}}
        ok, msg = um.delete_user("admin")
        assert ok is False
        assert "administrador" in msg

    def test_delete_nonexistent(self):
        um = _make_um()
        um.users = {}
        ok, msg = um.delete_user("ghost")
        assert ok is False

    def test_delete_sql_exception(self):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Delete error")

        um = _make_um()
        um.sql_engine = mock_engine
        um.users = {"victim": {"username": "victim"}}

        ok, msg = um.delete_user("victim")
        assert ok is True  # User removed from dict even if SQL fails
        assert "victim" not in um.users
