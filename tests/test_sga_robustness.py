import os
import time
import socket
import pytest
from unittest.mock import MagicMock, patch
from core.database_client import DatabaseClient
from core.system_health import check_sga_status

SGA_ENDPOINT = "/orders/api/sga/label-printed"
TEST_API_KEY = "test-sga-secret-key-2026"


class TestSgaRobustness:
    """Robustness and reliability tests for SGA integrations."""

    def test_webhook_auto_imports_from_sap(self, client, app):
        """Verify that when an order is not found locally, the webhook queries SAP Hana, auto-imports it, and updates it."""
        # Ensure SAP is marked available
        app.sap_available = True
        
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_order_details.return_value = {
            "header": {
                "order_number": "88888",
                "doc_entry": 888,
                "customer_code": "CUST888",
                "customer_name": "Customer 888",
                "order_date": "2026-06-10",
                "delivery_date": "2026-06-12",
                "total_value": 1500.00,
                "currency": "MXN",
                "sap_status": "Abierto",
                "factura_number": None,
                "delivery_number": None,
                "creator_name": "sap_user",
            },
            "items": [
                {"item_code": "ITEM-88", "quantity": 10}
            ]
        }
        
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False), \
             patch.object(app, "sap_connector", mock_sap):
             
            # Make the request for 88888 (which doesn't exist locally)
            resp = client.post(
                SGA_ENDPOINT,
                json={
                    "order_id": "88888",
                    "station": "Station88",
                    "items": ["ITEM-88"],
                },
                headers={"X-API-Key": TEST_API_KEY}
            )
            
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["order_id"] == "88888"
            assert data["new_status"] == "En Proceso"
            
            # Verify it was added to the local manager
            with app.app_context():
                order = app.order_status_mgr.get_order("88888")
                assert order is not None
                assert order["status"] == "En Proceso"
                assert order["customer_name"] == "Customer 888"

    @patch("core.database_client.pyodbc")
    @patch("core.database_client.load_dotenv")
    @patch("core.database_client.time.sleep")
    def test_database_client_connect_exponential_backoff(self, mock_sleep, _ld, mock_pyodbc):
        """Test that DatabaseClient.connect uses exponential backoff and retries upon connection failure."""
        db = DatabaseClient()
        mock_pyodbc.drivers.return_value = []
        
        # Fail 3 times, then succeed
        mock_conn = MagicMock()
        mock_pyodbc.connect.side_effect = [
            Exception("Conn error 1"),
            Exception("Conn error 2"),
            Exception("Conn error 3"),
            mock_conn
        ]
        
        with patch.dict(os.environ, {
            "SQL_SERVER": "test-server",
            "SQL_DATABASE": "test-db",
            "SQL_USER": "test-user",
            "SQL_PASSWORD": "test_pass",
        }, clear=False), \
             patch("core.database_client.create_engine") as mock_create_engine:
             
            result = db.connect(max_retries=5, retry_delay=1)
            
            assert result is True
            assert db.connected is True
            assert mock_pyodbc.connect.call_count == 4
            assert mock_sleep.call_count == 3
            
            # Verify exponential backoff intervals
            # Delay 1: 1 * 2^0 = 1 + jitter
            # Delay 2: 1 * 2^1 = 2 + jitter
            # Delay 3: 1 * 2^2 = 4 + jitter
            sleep_args = [call[0][0] for call in mock_sleep.call_args_list]
            assert 1.0 <= sleep_args[0] <= 1.5
            assert 2.0 <= sleep_args[1] <= 2.5
            assert 4.0 <= sleep_args[2] <= 4.5

    @patch("core.database_client.time.sleep")
    def test_execute_query_reconnect_retry(self, mock_sleep):
        """Test that execute_query retries query execution and performs reconnect if checkout/query fails."""
        db = DatabaseClient()
        
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        
        # Setup mock_engine
        db.engine = mock_engine
        db.connected = True
        
        # Raise exception on first query execution, return success on second
        mock_conn.exec_driver_sql.side_effect = [
            Exception("Query transient error"),
            MagicMock(fetchall=lambda: [("row2",)])
        ]
        
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        
        # Mock db.connect so that it recreates the mock engine upon reconnecting
        def mock_connect(*args, **kwargs):
            db.engine = mock_engine
            db.connected = True
            return True
            
        db.connect = MagicMock(side_effect=mock_connect)
        
        result = db.execute_query("SELECT ?", params=("val",), retries=3, delay=1)
        
        assert result == [("row2",)]
        assert db.connected is True
        # Verify connect was called to reconnect once engine was set to None after failure
        db.connect.assert_called_once()
        mock_sleep.assert_called_once()
        
        sleep_arg = mock_sleep.call_args[0][0]
        assert 1.0 <= sleep_arg <= 1.2

    @patch("core.system_health.socket.create_connection")
    @patch("core.system_health.time.sleep")
    def test_check_sga_status_retries_on_failure(self, mock_sleep, mock_create):
        """Test that check_sga_status retries the socket connection before reporting SGA offline."""
        # Ensure cache is expired
        from core.system_health import _sga_cache
        _sga_cache["timestamp"] = 0
        
        # Raise error twice, then succeed
        mock_create.side_effect = [
            OSError("Transient network drop"),
            OSError("Web port timeout"),
            MagicMock()  # success
        ]
        
        with patch.dict(os.environ, {"SQL_SERVER": "192.168.2.237", "SGA_WEB_HOST": "192.168.2.134"}, clear=False):
            status = check_sga_status(timeout=0.1, cache_ttl=0, max_attempts=3, retry_delay=0.1)
            
            assert status is True
            # First attempt (SQL fail -> Web fail) = 2 calls
            # Second attempt (SQL success) = 1 call
            # Total socket.create_connection calls = 3
            assert mock_create.call_count == 3
            mock_sleep.assert_called_once_with(0.1)
