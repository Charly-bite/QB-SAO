import json
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from core.relacion_manager import RelacionManager
from core.factura_metadata_manager import FacturaMetadataManager


class TestRelacionManagerNormalization:
    @pytest.fixture
    def temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @patch("core.relacion_manager.DatabaseClient")
    def test_ensure_table_exists_creates_child_table(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        mgr = RelacionManager(db_path=temp_db_path)
        
        # Verify ensure table exists executes create statements
        assert mock_conn.exec_driver_sql.call_count >= 3
        # Check that it executed queries mentioning the child table name
        called_queries = [args[0] for args, _ in mock_conn.exec_driver_sql.call_args_list]
        assert any("seguimiento_relacion_invoices" in q for q in called_queries)

    @patch("core.relacion_manager.DatabaseClient")
    def test_create_or_update_relacion_syncs_child_table(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        mgr = RelacionManager(db_path=temp_db_path)
        
        invoices = [
            {"invoice_number": "12345", "_selected": True, "shipping_type": "LOCAL", "observaciones": "Nota A"}
        ]
        
        mgr.create_or_update_relacion("2026-06-10", invoices, "admin")
        
        # Verify it ran the DELETE and INSERT for the child table
        called_queries = [args[0] for args, _ in mock_conn.exec_driver_sql.call_args_list]
        assert any("DELETE FROM seguimiento_relacion_invoices" in q for q in called_queries)
        assert any("INSERT INTO seguimiento_relacion_invoices" in q for q in called_queries)

    @patch("core.relacion_manager.DatabaseClient")
    def test_get_relacion_loads_from_child_table(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        # Mock parent query result
        mock_parent_row = (
            "RE-100626", "2026-06-10", None, None, "admin", "admin",
            "[]", "", "active", 0, None, "", None
        )
        # Mock child table rows query result
        mock_child_rows = [
            ("12345", 1, "LOCAL", "Nota A", json.dumps({"invoice_number": "12345"}))
        ]
        
        # Configure connection mock results
        mock_conn.exec_driver_sql.return_value.fetchone.return_value = mock_parent_row
        mock_conn.exec_driver_sql.return_value.fetchall.return_value = mock_child_rows

        mgr = RelacionManager(db_path=temp_db_path)
        rel = mgr.get_relacion("2026-06-10")
        
        assert rel is not None
        assert len(rel["invoices"]) == 1
        assert rel["invoices"][0]["invoice_number"] == "12345"
        assert rel["invoices"][0]["_selected"] is True
        assert rel["invoices"][0]["shipping_type"] == "LOCAL"
        assert rel["invoices"][0]["observaciones"] == "Nota A"

    @patch("core.relacion_manager.DatabaseClient")
    def test_get_relacion_self_healing_backfill(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        # Mock parent relation row with legacy invoices_json populated
        legacy_invoices = [{"invoice_number": "12345", "_selected": True, "shipping_type": "LOCAL", "observaciones": "Nota Legacy"}]
        mock_parent_row = (
            "RE-100626", "2026-06-10", None, None, "admin", "admin",
            json.dumps(legacy_invoices), "12345", "active", 0, None, "", None
        )
        
        # Mock connection return sequence: 
        # First execution (parent SELECT): returns parent row
        # Second execution (child SELECT): returns [] (0 rows, needs backfill)
        mock_conn.exec_driver_sql.return_value.fetchone.return_value = mock_parent_row
        mock_conn.exec_driver_sql.return_value.fetchall.return_value = []

        mgr = RelacionManager(db_path=temp_db_path)
        rel = mgr.get_relacion("2026-06-10")
        
        # Verify it backfilled the child table
        called_queries = [args[0] for args, _ in mock_conn.exec_driver_sql.call_args_list]
        assert any("INSERT INTO seguimiento_relacion_invoices" in q for q in called_queries)
        assert len(rel["invoices"]) == 1
        assert rel["invoices"][0]["invoice_number"] == "12345"


class TestFacturaMetadataManagerNormalization:
    @pytest.fixture
    def temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass

    @patch("core.factura_metadata_manager.DatabaseClient")
    def test_ensure_table_exists_creates_credit_table(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        mgr = FacturaMetadataManager(db_path=temp_db_path)
        
        called_queries = [args[0] for args, _ in mock_conn.exec_driver_sql.call_args_list]
        assert any("seguimiento_credito_autorizaciones" in q for q in called_queries)

    @patch("core.factura_metadata_manager.DatabaseClient")
    def test_get_credito_authorizations_self_healing(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        # Mock connection calls:
        # First query (new table SELECT): empty (needs backfill)
        # Second query (legacy table SELECT): returns 1 legacy row
        legacy_credit_row = (5001, 1, "AzucenaL", "2026-07-14T12:00:00", 0, "Nota Credito", 1)
        
        mock_conn.exec_driver_sql.return_value.fetchall.side_effect = [
            [],                  # from new table
            [legacy_credit_row]  # from legacy table
        ]

        mgr = FacturaMetadataManager(db_path=temp_db_path)
        auths = mgr.get_credito_authorizations()
        
        assert 5001 in auths
        assert auths[5001]["credito_authorized"] is True
        assert auths[5001]["credito_authorized_by"] == "AzucenaL"
        assert auths[5001]["credito_notes"] == "Nota Credito"
        
        # Verify it inserted into the new table
        called_queries = [args[0] for args, _ in mock_conn.exec_driver_sql.call_args_list]
        assert any("INSERT INTO seguimiento_credito_autorizaciones" in q for q in called_queries)

    @patch("core.factura_metadata_manager.DatabaseClient")
    def test_save_credito_methods_target_new_table(self, mock_db_client, temp_db_path):
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_db_client.return_value.engine = mock_engine

        mgr = FacturaMetadataManager(db_path=temp_db_path)
        
        mgr.save_credito_authorization(5001, True, "AzucenaL", "2026-07-14")
        mgr.mark_revoked_from_relacion(5001, True)
        mgr.save_credito_notes(5001, "Test note")
        mgr.save_sent_to_credito(5001, True)
        
        called_queries = [args[0] for args, _ in mock_conn.exec_driver_sql.call_args_list]
        # Assert that all queries targets the new normalized credit table
        assert all("UPDATE seguimiento_credito_autorizaciones" in q or "INSERT INTO seguimiento_credito_autorizaciones" in q for q in called_queries if "UPDATE" in q or "INSERT" in q)
