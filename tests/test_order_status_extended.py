"""
Extended tests for core.order_status_manager — covers SQL persistence
paths, bulk import, reconciliation, and export_for_web.
"""

import datetime
import json
import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest


def _make_osm(orders=None, sql_engine=None):
    """Create an OrderStatusManager with a temp JSON file, bypassing SQL."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8")
    seed = {"orders": orders or {}, "last_updated": datetime.datetime.now().isoformat()}
    json.dump(seed, tmp, ensure_ascii=False)
    tmp.close()

    with patch("core.database_client.DatabaseClient") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.connect.return_value = False
        mock_instance.get_sql_engine.return_value = sql_engine
        mock_cls.return_value = mock_instance
        from core.order_status_manager import OrderStatusManager
        osm = OrderStatusManager(db_path=tmp.name)

    return osm, tmp.name


def _sample_order(order_id="100", status="Pendiente", sap_status="Abierto"):
    return {
        "order_id": order_id,
        "customer_code": "C001",
        "customer_name": "Test Customer",
        "order_date": "2026-01-01",
        "delivery_date": "2026-01-10",
        "total": 1000.0,
        "currency": "MXN",
        "comments": "",
        "items": [{"ItemCode": "ITEM-A"}],
        "sap_status": sap_status,
        "status": status,
        "status_history": [],
        "imported_at": "2026-01-01T00:00:00",
        "last_updated": "2026-01-01T00:00:00",
        "updated_by": "system",
        "created_by": "system",
    }


class TestEnsureDbTableExists:
    def test_no_engine(self):
        osm, path = _make_osm()
        osm.sql_engine = None
        osm._ensure_db_table_exists()  # Should not raise
        os.unlink(path)

    def test_with_engine_success(self):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        osm, path = _make_osm()
        osm.sql_engine = mock_engine
        osm._ensure_db_table_exists()
        mock_conn.exec_driver_sql.assert_called_once()
        os.unlink(path)

    def test_with_engine_exception(self):
        mock_engine = MagicMock()
        mock_engine.begin.side_effect = Exception("SQL error")

        osm, path = _make_osm()
        osm.sql_engine = mock_engine
        osm._ensure_db_table_exists()  # Should not raise
        os.unlink(path)


class TestLoadDatabase:
    def test_load_from_json(self):
        orders = {"200": _sample_order("200")}
        osm, path = _make_osm(orders=orders)
        assert "200" in osm.orders
        os.unlink(path)

    def test_json_file_not_exists(self):
        osm, path = _make_osm()
        os.unlink(path)
        osm.db_path = "/nonexistent/path.json"
        osm.sql_engine = None
        osm._load_database()
        assert osm.orders == {}

    def test_json_decode_error(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8")
        tmp.write("INVALID JSON{{{")
        tmp.close()

        with patch("core.database_client.DatabaseClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.connect.return_value = False
            mock_instance.get_sql_engine.return_value = None
            mock_cls.return_value = mock_instance
            from core.order_status_manager import OrderStatusManager
            osm = OrderStatusManager(db_path=tmp.name)

        assert osm.orders == {}
        os.unlink(tmp.name)

    def test_normalize_labels_on_load(self):
        orders = {"300": _sample_order("300", status="Preparando")}
        osm, path = _make_osm(orders=orders)
        # "Preparando" should be migrated to "Entregado"
        assert osm.orders["300"]["status"] == "Entregado"
        os.unlink(path)

    def test_normalize_history_labels(self):
        order = _sample_order("301")
        order["status_history"] = [
            {"status": "Enviado", "previous_status": "Listo para Envío"}
        ]
        osm, path = _make_osm(orders={"301": order})
        h = osm.orders["301"]["status_history"][0]
        assert h["status"] == "Enviado al cliente"
        assert h["previous_status"] == "Relacion de envio"
        os.unlink(path)


class TestSaveDatabase:
    def test_save_json_success(self):
        osm, path = _make_osm(orders={"400": _sample_order("400")})
        result = osm._save_database()
        assert result is True
        with open(path, "r") as f:
            data = json.load(f)
        assert "400" in data["orders"]
        os.unlink(path)

    def test_save_json_io_error(self):
        osm, path = _make_osm()
        osm.db_path = "/nonexistent/dir/file.json"
        result = osm._save_database()
        assert result is False
        os.unlink(path)

    def test_save_sql_success(self):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_raw = MagicMock()
        mock_cursor = MagicMock()
        mock_raw.cursor.return_value = mock_cursor
        mock_conn.connection = mock_raw
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        osm, path = _make_osm(orders={"500": _sample_order("500")})
        osm.sql_engine = mock_engine
        osm._save_database()

        mock_cursor.execute.assert_called()
        mock_cursor.executemany.assert_called()
        mock_raw.commit.assert_called()
        os.unlink(path)

    def test_save_sql_exception(self):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("SQL write error")

        osm, path = _make_osm(orders={"501": _sample_order("501")})
        osm.sql_engine = mock_engine
        # Should not raise, falls through to JSON
        osm._save_database()
        os.unlink(path)


class TestImportFromSap:
    def test_new_order(self):
        osm, path = _make_osm()
        sap = {"DocNum": "600", "CardCode": "C100", "CardName": "Test"}
        result = osm.import_from_sap(sap, imported_by="user1")
        assert result["order_id"] == "600"
        assert result["status"] == "Pendiente"
        assert len(result["status_history"]) == 1
        os.unlink(path)

    def test_update_existing(self):
        orders = {"700": _sample_order("700", status="En Proceso")}
        osm, path = _make_osm(orders=orders)
        sap = {"DocNum": "700", "CardCode": "C200", "CardName": "Updated"}
        result = osm.import_from_sap(sap, imported_by="user2")
        assert result["status"] == "En Proceso"  # Preserved
        assert result["customer_name"] == "Updated"
        os.unlink(path)

    def test_missing_docnum_raises(self):
        osm, path = _make_osm()
        with pytest.raises(ValueError, match="order_id"):
            osm.import_from_sap({})
        os.unlink(path)


class TestBulkImportFromSap:
    def test_mixed_import(self):
        orders = {"800": _sample_order("800")}
        osm, path = _make_osm(orders=orders)
        sap_orders = [
            {"header": {"order_number": "800", "customer_code": "C1", "customer_name": "A"}},
            {"header": {"order_number": "801", "customer_code": "C2", "customer_name": "B"}},
        ]
        stats = osm.bulk_import_from_sap(sap_orders)
        assert stats["updated"] == 1
        assert stats["imported"] == 1
        assert stats["errors"] == 0
        os.unlink(path)

    def test_skip_missing_order_id(self):
        osm, path = _make_osm()
        sap_orders = [{"header": {"order_number": ""}}]
        stats = osm.bulk_import_from_sap(sap_orders)
        assert stats["imported"] == 0
        os.unlink(path)

    def test_error_in_batch(self):
        osm, path = _make_osm()
        sap_orders = [{"header": {"order_number": "99999"}}]
        with patch.object(osm, "import_from_sap", side_effect=Exception("err")):
            stats = osm.bulk_import_from_sap(sap_orders)
            assert stats["errors"] == 1
        os.unlink(path)


class TestReconcileStatuses:
    def test_cerrado_to_ready_with_factura(self):
        """Cerrado + factura_number → Facturacion."""
        order = _sample_order("900", status="Pendiente", sap_status="Cerrado")
        order["factura_number"] = "F-001"
        orders = {"900": order}
        osm, path = _make_osm(orders=orders)
        fixed = osm.reconcile_statuses()
        assert len(fixed) == 1
        assert osm.orders["900"]["status"] == "Facturacion"
        os.unlink(path)

    def test_cerrado_to_facturacion_without_factura(self):
        """Cerrado + no factura_number → Entregado (waiting for bill)."""
        orders = {"900": _sample_order("900", status="Pendiente", sap_status="Cerrado")}
        osm, path = _make_osm(orders=orders)
        fixed = osm.reconcile_statuses()
        assert len(fixed) == 1
        assert osm.orders["900"]["status"] == "Entregado"
        os.unlink(path)

    def test_cancelado_to_cancelled(self):
        orders = {"901": _sample_order("901", status="En Proceso", sap_status="Cancelado")}
        osm, path = _make_osm(orders=orders)
        fixed = osm.reconcile_statuses()
        assert len(fixed) == 1
        assert osm.orders["901"]["status"] == "Cancelado"
        os.unlink(path)

    def test_already_correct(self):
        orders = {"902": _sample_order("902", status="Cancelado", sap_status="Cancelado")}
        osm, path = _make_osm(orders=orders)
        fixed = osm.reconcile_statuses()
        assert len(fixed) == 0
        os.unlink(path)

    def test_cerrado_already_shipped(self):
        orders = {"903": _sample_order("903", status="Enviado al cliente", sap_status="Cerrado")}
        osm, path = _make_osm(orders=orders)
        fixed = osm.reconcile_statuses()
        assert len(fixed) == 0
        os.unlink(path)


class TestDeleteOrder:
    def test_delete_existing(self):
        orders = {"1000": _sample_order("1000")}
        osm, path = _make_osm(orders=orders)
        result = osm.delete_order("1000")
        assert result is True
        assert "1000" not in osm.orders
        os.unlink(path)

    def test_delete_nonexistent(self):
        osm, path = _make_osm()
        result = osm.delete_order("9999")
        assert result is False
        os.unlink(path)


class TestExportForWeb:
    def test_export_structure(self):
        orders = {"1100": _sample_order("1100")}
        osm, path = _make_osm(orders=orders)
        export = osm.export_for_web()
        assert "orders" in export
        assert "status_counts" in export
        assert "generated_at" in export
        assert len(export["orders"]) == 1
        assert export["orders"][0]["order_id"] == "1100"
        assert "item_count" in export["orders"][0]
        os.unlink(path)
