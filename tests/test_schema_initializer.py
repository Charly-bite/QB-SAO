"""
Unit tests for P3-01 Centralized Startup DDL Initializer (core/schema_initializer.py)
"""

from unittest.mock import MagicMock
import pytest
from core.schema_initializer import init_db_schema


def test_init_db_schema_returns_false_when_no_client():
    """Verify that init_db_schema handles None/unconnected db_client gracefully."""
    assert init_db_schema(None) is False

    mock_client = MagicMock()
    mock_client.engine = None
    assert init_db_schema(mock_client) is False


def test_init_db_schema_executes_sequential_ddl():
    """Verify that init_db_schema executes DDL statements on active engine."""
    mock_client = MagicMock()
    mock_engine = MagicMock()
    mock_conn = MagicMock()

    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_client.engine = mock_engine

    result = init_db_schema(mock_client)
    assert result is True
    assert mock_conn.exec_driver_sql.call_count >= 5
