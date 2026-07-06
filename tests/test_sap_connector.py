"""
Tests for core.sap_connector — SAPHanaConnector.

All hdbcli calls are mocked; no real SAP HANA connection is needed.
"""

import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_connector(**kwargs):
    """Create a SAPHanaConnector with mocked hdbcli.
    Provides test credentials by default so connect() works on CI where
    no .env file is present.
    """
    from core.sap_connector import SAPHanaConnector
    kwargs.setdefault("username", "test_user")
    kwargs.setdefault("password", "test_pass")
    return SAPHanaConnector(**kwargs)


# ---------------------------------------------------------------------------
# __init__ & properties
# ---------------------------------------------------------------------------


class TestSAPHanaConnectorInit:
    def test_defaults(self):
        """Verify the constructor reads defaults from class-level DEFAULT_* attributes."""
        from core.sap_connector import SAPHanaConnector
        c = SAPHanaConnector()  # raw constructor — no test defaults
        assert c.host == SAPHanaConnector.DEFAULT_HOST
        assert c.port == SAPHanaConnector.DEFAULT_PORT
        assert c.schema == SAPHanaConnector.DEFAULT_SCHEMA
        assert c.username == SAPHanaConnector.DEFAULT_USER

    def test_custom_params(self):
        c = _make_connector(host="10.0.0.1", port=30013, username="u", password="p", schema="S")
        assert c.host == "10.0.0.1"
        assert c.port == 30013
        assert c.username == "u"
        assert c.password == "p"
        assert c.schema == "S"

    def test_connected_property_default_false(self):
        c = _make_connector()
        assert c.connected is False

    def test_connection_property_default_none(self):
        c = _make_connector()
        assert c.connection is None


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


class TestConnectDisconnect:
    @patch("core.sap_connector.dbapi")
    def test_connect_success(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        result = c.connect()

        assert result is True
        assert c.connected is True
        assert c.connection is mock_conn
        mock_dbapi.connect.assert_called_once()

    @patch("core.sap_connector.dbapi")
    def test_connect_dbapi_error(self, mock_dbapi):
        mock_dbapi.Error = Exception
        mock_dbapi.connect.side_effect = Exception("Connection refused")

        c = _make_connector()
        with pytest.raises(Exception, match="Connection refused"):
            c.connect()

        assert c.connected is False
        assert c.connection is None

    @patch("core.sap_connector.dbapi")
    def test_connect_generic_exception(self, mock_dbapi):
        # Make dbapi.Error a class that does NOT match our exception
        mock_dbapi.Error = type("DBError", (Exception,), {})
        mock_dbapi.connect.side_effect = RuntimeError("Fatal")

        c = _make_connector()
        result = c.connect()

        assert result is False
        assert c.connected is False

    @patch("core.sap_connector.dbapi")
    def test_connect_with_custom_credentials(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        c.connect(username="custom_user", password="custom_pass")
        call_kwargs = mock_dbapi.connect.call_args
        assert call_kwargs[1]["user"] == "custom_user"
        assert call_kwargs[1]["password"] == "custom_pass"

    def test_connect_empty_credentials_raises(self):
        c = _make_connector()
        c.username = ""
        c.password = ""
        with pytest.raises(ValueError, match="Username and password"):
            c.connect(username="", password="")

    @patch("core.sap_connector.dbapi")
    def test_disconnect_active(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        c.disconnect()

        mock_conn.close.assert_called_once()
        assert c.connected is False

    def test_disconnect_no_connection(self):
        c = _make_connector()
        c.disconnect()  # Should not raise


# ---------------------------------------------------------------------------
# _get_table_name / _ensure_connected
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_get_table_name_with_schema(self):
        c = _make_connector(schema="MY_SCHEMA")
        result = c._get_table_name("sales_orders")
        assert '"MY_SCHEMA"' in result
        assert '"ORDR"' in result

    def test_get_table_name_without_schema(self):
        c = _make_connector()
        c.schema = ""
        result = c._get_table_name("sales_orders")
        assert result == '"ORDR"'

    def test_get_table_name_unknown_key(self):
        c = _make_connector(schema="S")
        result = c._get_table_name("custom_table")
        assert '"custom_table"' in result

    @patch("core.sap_connector.dbapi")
    def test_ensure_connected_already(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        c.connect()
        # Should not raise or reconnect
        c._ensure_connected()

    @patch("core.sap_connector.dbapi")
    def test_ensure_connected_auto_connect_success(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        assert c.connected is False
        c._ensure_connected()
        assert c.connected is True

    def test_ensure_connected_auto_connect_fail(self):
        c = _make_connector()
        mock_dbapi = MagicMock()
        mock_dbapi.Error = type("DBError", (Exception,), {})
        mock_dbapi.connect.side_effect = mock_dbapi.Error("fail")
        with patch("core.sap_connector.dbapi", mock_dbapi):
            with pytest.raises(ConnectionError, match="auto-connection failed"):
                c._ensure_connected()


# ---------------------------------------------------------------------------
# get_sales_orders
# ---------------------------------------------------------------------------


class TestGetSalesOrders:
    @patch("core.sap_connector.pd")
    @patch("core.sap_connector.dbapi")
    def test_get_sales_orders(self, mock_dbapi, mock_pd):
        mock_dbapi.connect.return_value = MagicMock()
        mock_pd.read_sql.return_value = MagicMock()

        c = _make_connector()
        c.connect()
        result = c.get_sales_orders(days_back=10, limit=100)

        mock_pd.read_sql.assert_called_once()
        assert result is not None


# ---------------------------------------------------------------------------
# get_recent_orders / get_all_open_orders
# ---------------------------------------------------------------------------


class TestGetRecentOrders:
    @patch("core.sap_connector.dbapi")
    def test_get_recent_orders(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # The batch implementation calls execute 3 times:
        # 1. Header query → returns full header rows (13 columns)
        # 2. Invoice query → returns (BaseEntry, DocNum) pairs
        # 3. Items query → returns line item rows (13 columns)
        header_rows = [
            # order_number, customer_code, customer_name, order_date, order_time,
            # delivery_date, total, currency, doc_entry, doc_status, canceled, printed, creator_name
            (100, "C001", "Customer A", "2026-01-01", 1430, "2026-01-10", 5000.0, "MXN", 1, "O", "N", "Y", "John"),
            (101, "C002", "Customer B", "2026-01-02", 0, "2026-01-11", 3000.0, "MXN", 2, "C", "N", "N", None),
        ]
        invoice_rows = [(1, 5001)]  # doc_entry=1 has invoice 5001
        delivery_rows = [(1, 6001)]  # doc_entry=1 has delivery 6001
        item_rows = [
            # doc_entry, line, item_code, desc, qty, unit, price, total, whs, tara, etiqueta, presentacion, kilos
            (1, 0, "ITEM-A", "Product A", 10.0, "KG", 100.0, 1000.0, "WH01", 0.5, 3, "25KG", 25.0),
        ]

        # Mock sequential fetchall calls
        mock_cursor.fetchall.side_effect = [header_rows, invoice_rows, delivery_rows, item_rows]
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()

        orders = c.get_recent_orders(limit=5, only_open=False)
        assert len(orders) == 2
        assert orders[0]["header"]["order_number"] == 100
        assert orders[0]["header"]["factura_number"] == "5001"
        assert len(orders[0]["items"]) == 1
        assert orders[1]["header"]["sap_status"] == "Cerrado"

    @patch("core.sap_connector.dbapi")
    def test_get_recent_orders_only_open(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        orders = c.get_recent_orders(limit=5, only_open=True)
        assert orders == []
        # Verify the WHERE clause includes DocStatus filter
        query = mock_cursor.execute.call_args[0][0]
        assert "DocStatus" in query

    @patch("core.sap_connector.dbapi")
    def test_get_recent_orders_no_connection(self, mock_dbapi):
        mock_dbapi.Error = type("DBError", (Exception,), {})
        mock_dbapi.connect.side_effect = RuntimeError("fail")
        c = _make_connector()
        c._local = threading.local()
        c._local.connected = True
        c._local.connection = None

        with pytest.raises(ConnectionError, match="No active connection"):
            c.get_recent_orders(limit=5)

    @patch("core.sap_connector.dbapi")
    def test_get_all_open_orders(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        result = c.get_all_open_orders()
        assert result == []


# ---------------------------------------------------------------------------
# get_order_details
# ---------------------------------------------------------------------------


class TestGetOrderDetails:
    def _setup_connector(self, mock_dbapi, header_row, inv_row=None, item_rows=None):
        """Helper to wire up mocked cursor responses."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        call_count = [0]

        def fake_fetchone():
            call_count[0] += 1
            if call_count[0] == 1:
                return header_row
            return inv_row

        mock_cursor.fetchone = fake_fetchone
        mock_cursor.fetchall.return_value = item_rows or []
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        return c

    @patch("core.sap_connector.dbapi")
    def test_order_not_found(self, mock_dbapi):
        c = self._setup_connector(mock_dbapi, header_row=None)
        result = c.get_order_details(99999)
        assert result is None

    @patch("core.sap_connector.dbapi")
    def test_order_open(self, mock_dbapi):
        # header: order_number, code, name, date, time, due, total, cur, entry, status, canceled, printed, creator, updater
        header = (100, "C001", "Customer", "2026-01-01", 1430, "2026-01-10", 5000.0, "MXN", 1, "O", "N", "Y", "John", "Jane")
        c = self._setup_connector(mock_dbapi, header_row=header, inv_row=None)
        result = c.get_order_details(100)

        assert result is not None
        assert result["header"]["sap_status"] == "Abierto"
        assert result["header"]["order_number"] == 100
        assert "14:30" in result["header"]["order_date"]

    @patch("core.sap_connector.dbapi")
    def test_order_closed(self, mock_dbapi):
        header = (101, "C001", "Customer", "2026-01-01", 0, "2026-01-10", 5000.0, "MXN", 2, "C", "N", "Y", "John", "Jane")
        c = self._setup_connector(mock_dbapi, header_row=header)
        result = c.get_order_details(101)
        assert result["header"]["sap_status"] == "Cerrado"
        # time=0 → no time in order_date
        assert ":" not in result["header"]["order_date"] or result["header"]["order_date"].endswith("2026-01-01")

    @patch("core.sap_connector.dbapi")
    def test_order_cancelled(self, mock_dbapi):
        header = (102, "C001", "Customer", "2026-01-01", None, "2026-01-10", 5000.0, "MXN", 3, "O", "Y", "N", None, None)
        c = self._setup_connector(mock_dbapi, header_row=header)
        result = c.get_order_details(102)
        assert result["header"]["sap_status"] == "Cancelado"
        assert result["header"]["creator_name"] == "SAP System"
        assert result["header"]["updater_name"] == "SAP System"

    @patch("core.sap_connector.dbapi")
    def test_order_with_invoice(self, mock_dbapi):
        header = (103, "C001", "Customer", "2026-01-01", 900, "2026-01-10", 5000.0, "MXN", 4, "O", "N", "Y", "John", "Jane")
        inv = (5001,)
        c = self._setup_connector(mock_dbapi, header_row=header, inv_row=inv)
        result = c.get_order_details(103)
        assert result["header"]["factura_number"] == "5001"

    @patch("core.sap_connector.dbapi")
    def test_order_with_items(self, mock_dbapi):
        header = (104, "C001", "Customer", "2026-01-01", 1200, "2026-01-10", 5000.0, "MXN", 5, "O", "N", "Y", "John", "Jane")
        items = [
            (0, "ITEM-A", "Product A", 10.0, "KG", 100.0, 1000.0, "WH01", 0.5, 3, "25KG", 25.0),
            (1, "ITEM-B", "Product B", None, "LT", None, None, "WH02", None, None, None, None),
        ]
        c = self._setup_connector(mock_dbapi, header_row=header, item_rows=items)
        result = c.get_order_details(104)
        assert len(result["items"]) == 2
        assert result["items"][0]["item_code"] == "ITEM-A"
        assert result["items"][0]["quantity"] == 10.0
        assert result["items"][1]["quantity"] == 0.0  # None → 0.0
        assert result["items"][1]["u_num_etiqueta"] == 0  # None → 0

    @patch("core.sap_connector.dbapi")
    def test_order_with_short_header(self, mock_dbapi):
        """Header row shorter than expected (no creator/updater)."""
        header = (105, "C001", "Customer", "2026-01-01", 1000, "2026-01-10", None, "MXN", 6, "O")
        c = self._setup_connector(mock_dbapi, header_row=header)
        result = c.get_order_details(105)
        assert result["header"]["total_value"] == 0  # None → 0
        assert result["header"]["doc_status"] == "O"

    @patch("core.sap_connector.dbapi")
    def test_order_no_connection(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        c._local = threading.local()
        c._local.connected = True
        c._local.connection = None
        with pytest.raises(ConnectionError):
            c.get_order_details(999)


# ---------------------------------------------------------------------------
# get_orders_status_batch
# ---------------------------------------------------------------------------


class TestGetOrdersStatusBatch:
    @patch("core.sap_connector.dbapi")
    def test_empty_list(self, mock_dbapi):
        c = _make_connector()
        assert c.get_orders_status_batch([]) == {}

    @patch("core.sap_connector.dbapi")
    def test_batch_success(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (100, "O", "N", "Customer A", "Seller X"),
            (101, "C", "N", "Customer B", None),
            (102, "O", "Y", "Customer C", "Seller Y"),
        ]
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        result = c.get_orders_status_batch([100, 101, 102])

        assert result[100]["sap_status"] == "Abierto"
        assert result[101]["sap_status"] == "Cerrado"
        assert result[102]["sap_status"] == "Cancelado"
        assert result[101]["updater_name"] == "SAP System"  # None → "SAP System"

    @patch("core.sap_connector.dbapi")
    def test_batch_exception_reconnect(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.side_effect = Exception("Query error")
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        result = c.get_orders_status_batch([100])
        assert result == {}  # Error path returns empty

    @patch("core.sap_connector.dbapi")
    def test_batch_no_connection(self, mock_dbapi):
        mock_dbapi.connect.return_value = MagicMock()
        c = _make_connector()
        c._local = threading.local()
        c._local.connected = True
        c._local.connection = None

        result = c.get_orders_status_batch([100])
        assert result == {}


class TestGetInvoiceRelationshipMap:
    @patch("core.sap_connector.dbapi")
    def test_get_relationship_map_not_found(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        result = c.get_invoice_relationship_map(12345)
        assert result is None

    @patch("core.sap_connector.dbapi")
    def test_get_relationship_map_success(self, mock_dbapi):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        # Mock fetchone calls
        inv_row = (
            10,         # DocEntry
            12345,      # DocNum
            "2026-06-19", # DocDate
            15000.0,    # DocTotal
            "MXN",      # DocCur
            "O",        # DocStatus
            "N",        # CANCELED
            5000.0,     # PaidToDate
            "CL-TEST",  # CardCode
            "Test Customer" # CardName
        )
        del_row = (
            20,         # DocEntry
            54321,      # DocNum
            "2026-06-18", # DocDate
            15000.0,    # DocTotal
            "MXN",      # DocCur
            "C",        # DocStatus
            "N"         # CANCELED
        )
        ord_row = (
            30,         # DocEntry
            98765,      # DocNum
            "2026-06-17", # DocDate
            15000.0,    # DocTotal
            "MXN",      # DocCur
            "C",        # DocStatus
            "N"         # CANCELED
        )
        mock_cursor.fetchone.side_effect = [inv_row, del_row, ord_row]

        # Mock fetchall call for payments
        pay_rows = [
            (
                40,          # DocEntry
                2222,        # DocNum
                "2026-06-19", # DocDate
                5000.0,      # DocTotal
                "MXN",       # DocCur
                "N",         # Canceled
                5000.0       # SumApplied
            )
        ]
        mock_cursor.fetchall.return_value = pay_rows

        mock_conn.cursor.return_value = mock_cursor
        mock_dbapi.connect.return_value = mock_conn

        c = _make_connector()
        c.connect()
        result = c.get_invoice_relationship_map(12345)

        assert result is not None
        assert result["invoice"]["doc_num"] == 12345
        assert result["invoice"]["status"] == "Abierto"
        assert result["delivery"]["doc_num"] == 54321
        assert result["delivery"]["status"] == "Cerrado"
        assert result["order"]["doc_num"] == 98765
        assert len(result["payments"]) == 1
        assert result["payments"][0]["doc_num"] == 2222
        assert result["payments"][0]["applied_total"] == 5000.0
        assert result["customer"]["card_name"] == "Test Customer"

