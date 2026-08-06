"""
Tests for core.database_client — DatabaseClient.

All pyodbc / SQLAlchemy calls are mocked.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure integrated security is disabled by default for legacy tests
import os
os.environ["SQL_INTEGRATED_SECURITY"] = "no"


class TestDatabaseClientInit:
    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_defaults(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        assert db.engine is None
        assert db.connected is False
        assert db._connection_string is None


class TestBuildConnectionString:
    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_with_sql_driver_env(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_DRIVER": "{Custom Driver}",
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "pass123",
            "SQL_INTEGRATED_SECURITY": "no"
        }):
            cs = db._build_connection_string()
        assert "Custom Driver" in cs
        assert "pass123" in cs

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_auto_detect_preferred_driver(self, _ld, mock_pyodbc):
        mock_pyodbc.drivers.return_value = [
            "SQL Server",
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 18 for SQL Server",
        ]
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_DRIVER": "",
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "p"
        }, clear=False):
            cs = db._build_connection_string()
        assert "ODBC Driver 18 for SQL Server" in cs

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_auto_detect_fallback_driver(self, _ld, mock_pyodbc):
        mock_pyodbc.drivers.return_value = ["Some SQL Server Driver"]
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_DRIVER": "",
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "p"
        }, clear=False):
            cs = db._build_connection_string()
        assert "Some SQL Server Driver" in cs

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_auto_detect_no_drivers(self, _ld, mock_pyodbc):
        mock_pyodbc.drivers.return_value = []
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_DRIVER": "",
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "p"
        }, clear=False):
            cs = db._build_connection_string()
        assert "ODBC Driver 17" in cs

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_auto_detect_exception(self, _ld, mock_pyodbc):
        mock_pyodbc.drivers.side_effect = Exception("No ODBC")
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_DRIVER": "",
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "p"
        }, clear=False):
            cs = db._build_connection_string()
        assert "ODBC Driver 17" in cs

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_missing_password_raises(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "",
            "SQL_INTEGRATED_SECURITY": "no"
        }, clear=False):
            with pytest.raises(ValueError, match="Missing required SQL environment config"):
                db._build_connection_string()

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_integrated_security(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_INTEGRATED_SECURITY": "yes",
            "SQL_USER": "",
            "SQL_PASSWORD": ""
        }, clear=False):
            cs = db._build_connection_string()
        assert "Trusted_Connection=yes" in cs
        assert "UID=" not in cs
        assert "PWD=" not in cs


class TestConnect:
    @patch("core.database_client.create_engine")
    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_connect_success(self, _ld, mock_pyodbc, mock_create_engine):
        mock_pyodbc.drivers.return_value = []
        mock_conn = MagicMock()
        mock_pyodbc.connect.return_value = mock_conn
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "test_pass"
        }, clear=False):
            result = db.connect()

        assert result is True
        assert db.connected is True
        assert db.engine is mock_engine
        mock_conn.close.assert_called_once()

    @patch("core.database_client.create_engine")
    @patch("pymssql.connect")
    @patch("core.database_client.load_dotenv")
    def test_connect_pymssql_success(self, _ld, mock_pymssql_connect, mock_create_engine):
        mock_conn = MagicMock()
        mock_pymssql_connect.return_value = mock_conn
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "test_pass",
            "SQL_USE_PYMSSQL": "yes",
            "TEST_USE_PYMSSQL": "yes"
        }, clear=False):
            result = db.connect()

        assert result is True
        assert db.connected is True
        assert db.engine is mock_engine
        mock_conn.close.assert_called_once()
        mock_pymssql_connect.assert_called_once_with(
            server="127.0.0.1",
            user="usr",
            password="test_pass",
            database="DB",
            login_timeout=5
        )

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    @patch("core.database_client.time.sleep")
    def test_connect_failure(self, mock_sleep, _ld, mock_pyodbc):
        mock_pyodbc.drivers.return_value = []
        mock_pyodbc.connect.side_effect = Exception("Connection failed")

        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "test_pass"
        }, clear=False):
            result = db.connect(max_retries=3)

        assert result is False
        assert db.connected is False
        assert db.engine is None
        assert mock_pyodbc.connect.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("core.database_client.create_engine")
    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    @patch("core.database_client.time.sleep")
    def test_connect_retry_success(self, mock_sleep, _ld, mock_pyodbc, mock_create_engine):
        mock_pyodbc.drivers.return_value = []
        mock_conn = MagicMock()
        # Fail first, then succeed
        mock_pyodbc.connect.side_effect = [Exception("Timeout"), mock_conn]
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with patch.dict(os.environ, {
            "SQL_SERVER": "127.0.0.1",
            "SQL_DATABASE": "DB",
            "SQL_USER": "usr",
            "SQL_PASSWORD": "test_pass"
        }, clear=False):
            result = db.connect(max_retries=3)

        assert result is True
        assert db.connected is True
        assert db.engine is mock_engine
        assert mock_pyodbc.connect.call_count == 2
        assert mock_sleep.call_count == 1
        mock_conn.close.assert_called_once()


class TestGetSqlEngine:
    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_returns_engine(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        mock_engine = MagicMock()
        db.engine = mock_engine
        assert db.get_sql_engine() is mock_engine


class TestExecuteQuery:
    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_not_connected(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        with pytest.raises(ConnectionError, match="Not connected"):
            db.execute_query("SELECT 1")

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_with_params(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("row1",)]
        mock_conn.exec_driver_sql.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        db.engine = mock_engine

        result = db.execute_query("SELECT ?", params=("val",))
        assert result == [("row1",)]
        mock_conn.exec_driver_sql.assert_called_with("SELECT ?", ("val",))

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    def test_without_params(self, _ld, _pyodbc):
        from core.database_client import DatabaseClient
        db = DatabaseClient()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_conn.exec_driver_sql.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        db.engine = mock_engine

        result = db.execute_query("SELECT 1")
        assert result == []
        mock_conn.exec_driver_sql.assert_called_with("SELECT 1")
