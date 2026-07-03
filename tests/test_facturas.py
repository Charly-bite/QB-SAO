"""
Tests for the Facturas del Día feature.

Covers:
- SAPHanaConnector.get_todays_invoices()
- SAPHanaConnector.get_invoice_lines()
- /orders/facturas page route
- /orders/api/facturas JSON API
"""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SAP Connector — get_todays_invoices
# ---------------------------------------------------------------------------


def _make_connector(**kwargs):
    from core.sap_connector import SAPHanaConnector
    kwargs.setdefault("username", "test_user")
    kwargs.setdefault("password", "test_pass")
    return SAPHanaConnector(**kwargs)


class TestGetTodaysInvoices:
    @patch("core.sap_connector.dbapi")
    def test_default_date(self, mock_dbapi):
        """No date_str → uses CURRENT_DATE."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (5001, 1, "C1", "Cust 1", "2026-05-21", 100.50, "MXN", "O", "N", "Note", "Seller 1", 0.0, "LOCAL", "CONTADO", "WHS1", 17001, "2026-05-20"),
            (5002, 2, "C2", "Cust 2", "2026-05-21", 200.00, "USD", "O", "N", "", "Seller 2", 200.0, "PAQUETERIA", "CREDITO", "WHS2", None, None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        invoices = c.get_todays_invoices()

        assert len(invoices) == 2
        inv = invoices[0]
        assert inv["invoice_number"] == 5001
        assert inv["customer_name"] == "Cust 1"
        assert inv["total"] == 100.50
        assert inv["currency"] == "MXN"
        assert inv["status"] == "Abierta"
        assert inv["seller_name"] == "Seller 1"

        # Verify CURRENT_DATE is used in query
        query = mock_cursor.execute.call_args[0][0]
        assert "CURRENT_DATE" in query

    @patch("core.sap_connector.dbapi")
    def test_custom_date(self, mock_dbapi):
        """date_str provided → uses literal date."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        invoices = c.get_todays_invoices(date_str="2026-01-15")

        assert invoices == []
        query = mock_cursor.execute.call_args[0][0]
        assert "2026-01-15" in query

    @patch("core.sap_connector.dbapi")
    def test_closed_invoice(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (5002, 2, "C002", "Customer B", "2026-05-21", 8000.0, "USD", "C", "N", "", None, 0.0, "LOCAL", "CONTADO", "01", 1001, "2026-05-20"),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        invoices = c.get_todays_invoices()

        assert invoices[0]["status"] == "Cerrada"
        assert invoices[0]["seller_name"] == "SAP System"  # None fallback

    @patch("core.sap_connector.dbapi")
    def test_cancelled_invoice(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (5003, 3, None, None, "2026-05-21", None, None, None, "Y", None, None, 0.0, "LOCAL", "CONTADO", None, None, None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        invoices = c.get_todays_invoices()

        inv = invoices[0]
        assert inv["status"] == "Cancelada"
        assert inv["customer_code"] == ""
        assert inv["customer_name"] == ""
        assert inv["total"] == 0.0
        assert inv["currency"] == "MXN"
        assert inv["comments"] == ""

    @patch("core.sap_connector.dbapi")
    def test_no_connection(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        c._local = threading.local()
        c._local.connected = True
        c._local.connection = None

        with pytest.raises(ConnectionError, match="No active connection"):
            c.get_todays_invoices()


# ---------------------------------------------------------------------------
# SAP Connector — get_invoice_lines
# ---------------------------------------------------------------------------


class TestGetInvoiceLines:
    @patch("core.sap_connector.dbapi")
    def test_success(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (0, "ITEM-A", "Product A", 10.0, "KG", 100.0, 1000.0, "WH01"),
            (1, "ITEM-B", "Product B", None, None, None, None, None),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        items = c.get_invoice_lines(doc_entry=1)

        assert len(items) == 2
        assert items[0]["item_code"] == "ITEM-A"
        assert items[0]["quantity"] == 10.0
        assert items[0]["line_total"] == 1000.0
        assert items[1]["quantity"] == 0.0  # None → 0.0
        assert items[1]["unit"] == ""
        assert items[1]["warehouse"] == ""

    @patch("core.sap_connector.dbapi")
    def test_empty_result(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        items = c.get_invoice_lines(doc_entry=999)
        assert items == []

    @patch("core.sap_connector.dbapi")
    def test_no_connection(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        c._local = threading.local()
        c._local.connected = True
        c._local.connection = None

        with pytest.raises(ConnectionError, match="No active connection"):
            c.get_invoice_lines(doc_entry=1)


# ---------------------------------------------------------------------------
# /orders/facturas page
# ---------------------------------------------------------------------------


class TestFacturasPage:
    def test_renders_template(self, auth_client, app):
        resp = auth_client.get("/orders/facturas")
        assert resp.status_code == 200
        assert b"Facturas" in resp.data or b"facturas" in resp.data

    def test_requires_login(self, client, app):
        resp = client.get("/orders/facturas")
        # Should redirect to login
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# /orders/api/facturas JSON API
# ---------------------------------------------------------------------------


class TestApiFacturas:
    def test_sap_unavailable(self, auth_client, app):
        app.sap_available = False
        resp = auth_client.get("/orders/api/facturas")
        assert resp.status_code == 503
        data = resp.get_json()
        assert data["invoices"] == []
        app.sap_available = True

    def test_success(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_todays_invoices.return_value = [
            {
                "invoice_number": 5001,
                "doc_entry": 1,
                "customer_code": "C001",
                "customer_name": "Customer A",
                "invoice_date": "2026-05-21",
                "total": 10000.0,
                "currency": "MXN",
                "status": "Abierta",
                "doc_status": "O",
                "canceled": "N",
                "comments": "",
                "seller_name": "Seller X",
            },
            {
                "invoice_number": 5002,
                "doc_entry": 2,
                "customer_code": "C002",
                "customer_name": "Customer B",
                "invoice_date": "2026-05-21",
                "total": 5000.0,
                "currency": "USD",
                "status": "Cancelada",
                "doc_status": "O",
                "canceled": "Y",
                "comments": "Cancelled",
                "seller_name": "Seller Y",
            },
        ]
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/facturas")
        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data["invoices"]) == 2
        assert data["stats"]["total_count"] == 2
        assert data["stats"]["active_count"] == 1
        assert data["stats"]["cancelled_count"] == 1
        assert data["stats"]["total_mxn"] == 10000.0
        assert data["stats"]["total_usd"] == 5000.0
        assert "generated_at" in data

    def test_with_date_filter(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_todays_invoices.return_value = []
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/facturas?date=2026-01-15")
        assert resp.status_code == 200
        mock_sap.get_todays_invoices.assert_called_once_with(date_str="2026-01-15", extra_invoice_numbers=None)

    def test_empty_invoices(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_todays_invoices.return_value = []
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/facturas")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["invoices"] == []
        assert data["stats"]["total_count"] == 0

    def test_sap_exception(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_todays_invoices.side_effect = Exception("SAP connection lost")
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/facturas")
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data
        assert data["invoices"] == []

    def test_requires_login(self, client, app):
        app.sap_available = True
        resp = client.get("/orders/api/facturas")
        assert resp.status_code in (302, 401)


class TestApiFacturasRelationshipMap:
    def test_requires_login(self, client):
        resp = client.get("/orders/api/facturas/12345/relationship-map")
        assert resp.status_code in (302, 401)

    def test_sap_available_success(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_data = {
            "invoice": {"doc_num": 12345, "status": "Abierto", "total": 150.0},
            "delivery": None,
            "order": None,
            "payments": [],
            "customer": {"card_code": "C1", "card_name": "Cust 1"}
        }
        mock_sap.get_invoice_relationship_map.return_value = mock_data
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/facturas/12345/relationship-map")
        assert resp.status_code == 200
        res_data = resp.get_json()
        assert res_data["success"] is True
        assert res_data["data"]["invoice"]["doc_num"] == 12345

    def test_sap_available_not_found(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_invoice_relationship_map.return_value = None
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/facturas/12345/relationship-map")
        assert resp.status_code == 404
        res_data = resp.get_json()
        assert res_data["success"] is False
        assert "no encontrada" in res_data["error"]

    def test_sap_unavailable_fallback(self, auth_client, app):
        app.sap_available = False
        
        # Test simulated fallback response
        resp = auth_client.get("/orders/api/facturas/12345/relationship-map")
        assert resp.status_code == 200
        res_data = resp.get_json()
        assert res_data["success"] is True
        assert res_data["simulated"] is True
        assert res_data["data"]["invoice"]["doc_num"] == 12345
        assert res_data["data"]["order"]["doc_num"] == 12245  # fallback subtraction (invoice_number - 100)
        app.sap_available = True

