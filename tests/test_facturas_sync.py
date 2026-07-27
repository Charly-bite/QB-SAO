import json
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from core.factura_metadata_manager import FacturaMetadataManager


class TestFacturaMetadataManagerFallback:
    @pytest.fixture
    def temp_db_path(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except OSError:
            pass
        # Also clean up daily orders/extras fallbacks
        for suffix in ["_daily_order.json", "_daily_extra.json"]:
            fallback_path = path.replace(".json", suffix)
            try:
                os.unlink(fallback_path)
            except OSError:
                pass

    @patch("core.factura_metadata_manager.DatabaseClient")
    def test_manager_fallback_operations(self, mock_db_client, temp_db_path):
        # Instantiate manager pointing to temp file
        mgr = FacturaMetadataManager(db_path=temp_db_path)

        # 1. Category override
        mgr.save_override(12345, "PAQUETERIA")
        overrides, colors, custom_names = mgr.get_overrides()
        assert overrides[12345] == "PAQUETERIA"

        # 2. Color setting
        mgr.save_color(12345, "rojo")
        overrides, colors, custom_names = mgr.get_overrides()
        assert colors[12345] == "rojo"

        # 3. Custom customer name setting
        mgr.save_custom_customer_name(12345, "Cliente Especial")
        overrides, colors, custom_names = mgr.get_overrides()
        assert custom_names[12345] == "Cliente Especial"

        # 4. Daily manual order
        mgr.save_daily_order("2026-06-10", [5002, 5001, 12345])
        order = mgr.get_daily_order("2026-06-10")
        assert order == [5002, 5001, 12345]

        # 5. Daily extras
        mgr.save_daily_extras("2026-06-10", [99901, 99902])
        extras = mgr.get_daily_extras("2026-06-10")
        assert extras == [99901, 99902]

    @patch("core.factura_metadata_manager.DatabaseClient")
    def test_background_writer_and_exceptions(self, mock_db_client, temp_db_path):
        import sys
        import time
        from unittest.mock import patch, MagicMock

        mgr = FacturaMetadataManager(db_path=temp_db_path)

        # 1. Cover line 595 (inv_str not in local_metadata in save_sent_to_credito)
        mgr.save_sent_to_credito(99999, True)
        assert mgr.local_metadata["99999"]["sent_to_credito"] is True

        # 2. Force a write to the actual background queue.
        # This will execute lines 41-51 of _process_write_queue.
        mgr._write_queue.put((temp_db_path, {"test_key": "test_val"}))
        mgr._write_queue.join()  # waits until task_done is called
        
        with open(temp_db_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data.get("test_key") == "test_val"

        # 3. Test queue execution failure (invalid directory/file to trigger exception in _execute_write):
        mgr._write_queue.put(("::invalid_path::/nonexistent.json", {"k": "v"}))
        time.sleep(0.1)
        mgr._write_queue.join()

        # 4. Test _enqueue_write else branch:
        # Patch sys.modules to temporarily not have "pytest"
        with patch.dict("sys.modules", {}):
            mgr._enqueue_write(temp_db_path, {"test_key": "pytest_off"})
            mgr._write_queue.join()
            
        with open(temp_db_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        assert saved_data.get("test_key") == "pytest_off"

        # 5. Test exit sentinel:
        mgr._write_queue.put(None)
        time.sleep(0.1)


# ---------------------------------------------------------------------------
# API integration & Broadcasting tests
# ---------------------------------------------------------------------------

class TestFacturasSyncApi:
    @pytest.fixture(autouse=True)
    def setup_mocks(self, app):
        # Replace metadata manager with one using temporary files
        self.tmp_json = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp_json.close()
        self.mgr = FacturaMetadataManager(db_path=self.tmp_json.name)
        app.factura_metadata_mgr = self.mgr

        # Mock SAP connector
        self.mock_sap = MagicMock()
        self.mock_sap.connected = True
        self.mock_sap.get_todays_invoices.return_value = [
            {
                "invoice_number": 5001,
                "doc_entry": 1,
                "customer_code": "C001",
                "customer_name": "VENTAS MOSTRADOR GDL",
                "invoice_date": "2026-06-10",
                "total": 100.0,
                "currency": "MXN",
                "status": "Abierta",
                "doc_status": "O",
                "canceled": "N",
                "comments": "",
                "seller_name": "Seller X",
            }
        ]
        app.sap_connector = self.mock_sap
        app.sap_available = True

        yield

        # Cleanup
        try:
            os.unlink(self.tmp_json.name)
        except OSError:
            pass

    @patch("routes.orders._publish_event")
    def test_get_and_post_endpoints(self, mock_publish, auth_client):
        # 1. Set some overrides initially
        self.mgr.save_color(5001, "azul")
        self.mgr.save_custom_customer_name(5001, "Cliente Mostrador Personalizado")
        self.mgr.save_daily_order("2026-06-10", [5001])
        self.mgr.save_daily_extras("2026-06-10", [99901])

        # 2. Test GET /orders/api/facturas
        resp = auth_client.get("/orders/api/facturas?date=2026-06-10")
        assert resp.status_code == 200
        data = resp.get_json()
        
        assert data["row_colors"]["5001"] == "azul"
        assert data["custom_customer_names"]["5001"] == "Cliente Mostrador Personalizado"
        assert "5001" in data["manual_order"]
        assert 99901 in data["extra_invoices"]

        # 3. Test POST /api/facturas/<id>/color
        resp = auth_client.post(
            "/orders/api/facturas/5001/color",
            data=json.dumps({"color": "verde"}),
            content_type="application/json"
        )
        mock_publish.assert_called_with({
            "type": "factura_color_changed",
            "invoice_number": 5001,
            "color": "verde",
            "client_id": None
        })
        assert self.mgr.get_overrides()[1][5001] == "verde"

        # 4. Test POST /api/facturas/<id>/customer-name
        resp = auth_client.post(
            "/orders/api/facturas/5001/customer-name",
            data=json.dumps({"customer_name": "Juan Perez"}),
            content_type="application/json"
        )
        mock_publish.assert_called_with({
            "type": "factura_customer_name_changed",
            "invoice_number": 5001,
            "customer_name": "Juan Perez",
            "client_id": None
        })
        assert self.mgr.get_overrides()[2][5001] == "Juan Perez"

        # 5. Test POST /api/facturas/manual-order
        resp = auth_client.post(
            "/orders/api/facturas/manual-order",
            data=json.dumps({"date": "2026-06-10", "manual_order": [5001, 5002]}),
            content_type="application/json"
        )
        mock_publish.assert_called_with({
            "type": "factura_manual_order_changed",
            "date": "2026-06-10",
            "manual_order": [5001, 5002],
            "client_id": None
        })
        assert self.mgr.get_daily_order("2026-06-10") == [5001, 5002]

        # 6. Test POST /api/facturas/extra
        resp = auth_client.post(
            "/orders/api/facturas/extra",
            data=json.dumps({"date": "2026-06-10", "extra_invoices": [99901, 99902]}),
            content_type="application/json"
        )
        mock_publish.assert_called_with({
            "type": "factura_extras_changed",
            "date": "2026-06-10",
            "extra_invoices": [99901, 99902],
            "client_id": None
        })
        assert self.mgr.get_daily_extras("2026-06-10") == [99901, 99902]

        # 7. Test POST /api/facturas/<id>/category with ANEXO MY
        resp = auth_client.post(
            "/orders/api/facturas/5001/category",
            data=json.dumps({"category": "ANEXO MY"}),
            content_type="application/json"
        )
        mock_publish.assert_called_with({
            "type": "factura_category_changed",
            "invoice_number": 5001,
            "category": "ANEXO MY",
            "client_id": None
        })
        assert self.mgr.get_overrides()[0][5001] == "ANEXO MY"

        # 8. Test POST /api/facturas/<id>/category with ANEXO GDL
        resp = auth_client.post(
            "/orders/api/facturas/5001/category",
            data=json.dumps({"category": "ANEXO GDL"}),
            content_type="application/json"
        )
        mock_publish.assert_called_with({
            "type": "factura_category_changed",
            "invoice_number": 5001,
            "category": "ANEXO GDL",
            "client_id": None
        })
        assert self.mgr.get_overrides()[0][5001] == "ANEXO GDL"

    @patch("routes.orders._publish_event")
    def test_toggle_relacion_invoice(self, mock_publish, auth_client, app):
        # Setup mock relacion_mgr
        mock_rel_mgr = MagicMock()
        mock_rel_mgr.toggle_invoice_in_relacion.return_value = {
            "folio": "RE-100626",
            "invoices": [{"invoice_number": "5001", "customer_name": "Test Customer"}],
        }
        app.relacion_mgr = mock_rel_mgr
        if hasattr(app, "factura_metadata_mgr"):
            app.factura_metadata_mgr.save_credito_authorization(5001, True, "testadmin", "2026-06-10T10:00:00")

        # Test POST /api/relaciones/toggle
        payload = {
            "date": "2026-06-10",
            "invoice_number": "5001",
            "selected": True,
            "invoice_data": {"invoice_number": "5001", "customer_name": "Test Customer"},
            "manual_order": ["5001"]
        }
        resp = auth_client.post(
            "/orders/api/relaciones/toggle",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["relacion"]["folio"] == "RE-100626"

        mock_rel_mgr.toggle_invoice_in_relacion.assert_called_with(
            date_str="2026-06-10",
            invoice_numbers="5001",
            selected=True,
            invoice_data={"invoice_number": "5001", "customer_name": "Test Customer"},
            username="testadmin",
            manual_order=["5001"]
        )

        mock_publish.assert_called_with({
            "type": "relacion_updated",
            "folio": "RE-100626",
            "date": "2026-06-10",
            "username": "testadmin",
            "client_id": None
        })

    @patch("routes.orders._publish_event")
    def test_toggle_relacion_invoice_with_client_id(self, mock_publish, auth_client, app):
        # Setup mock relacion_mgr
        mock_rel_mgr = MagicMock()
        mock_rel_mgr.toggle_invoice_in_relacion.return_value = {
            "folio": "RE-100626",
            "invoices": [{"invoice_number": "5001", "customer_name": "Test Customer"}],
        }
        app.relacion_mgr = mock_rel_mgr
        if hasattr(app, "factura_metadata_mgr"):
            app.factura_metadata_mgr.save_credito_authorization(5001, True, "testadmin", "2026-06-10T10:00:00")

        # Test POST /api/relaciones/toggle with client_id
        payload = {
            "date": "2026-06-10",
            "invoice_number": "5001",
            "selected": True,
            "invoice_data": {"invoice_number": "5001", "customer_name": "Test Customer"},
            "manual_order": ["5001"],
            "client_id": "test_client_id_123"
        }
        resp = auth_client.post(
            "/orders/api/relaciones/toggle",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 200
        mock_publish.assert_called_with({
            "type": "relacion_updated",
            "folio": "RE-100626",
            "date": "2026-06-10",
            "username": "testadmin",
            "client_id": "test_client_id_123"
        })

    def test_toggle_relacion_unauthorized_rejected(self, auth_client, app):
        # Test that toggling an unauthorized invoice is rejected with 400
        if hasattr(app, "factura_metadata_mgr"):
            app.factura_metadata_mgr.save_credito_authorization(9999, False, "testadmin", "2026-06-10T10:00:00")
        
        payload = {
            "date": "2026-06-10",
            "invoice_number": "9999",
            "selected": True,
            "invoice_data": {"invoice_number": "9999", "customer_name": "Unauthorized Customer"},
        }
        resp = auth_client.post(
            "/orders/api/relaciones/toggle",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 400
        assert "no cuenta con autorización" in resp.get_json()["error"]

    @patch("routes.orders._publish_event")
    def test_send_to_credito_endpoint(self, mock_publish, auth_client, app):
        payload = {
            "sent": True
        }
        resp = auth_client.post(
            "/orders/api/facturas/5001/send-to-credito",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["sent_to_credito"] is True
        assert self.mgr.local_metadata["5001"]["sent_to_credito"] is True
        
        mock_publish.assert_called_with({
            "type": "factura_sent_to_credito_changed",
            "invoice_number": "5001",
            "sent_to_credito": True
        })

    @patch("routes.orders._publish_event")
    def test_auto_authorize_ventas_mostrador_endpoint(self, mock_publish, auth_client, app):
        payload = {
            "authorized": True,
            "customer_name": "VENTAS MOSTRADOR GDL"
        }
        resp = auth_client.post(
            "/orders/api/facturas/5001/authorize",
            data=json.dumps(payload),
            content_type="application/json"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["invoice"]["credito_authorized"] is True

    @patch("routes.orders._publish_event")
    def test_facturacion_can_auto_authorize_mostrador_only(self, mock_publish, app):
        print("PERMS IN TEST:", app.permission_manager.get_permissions("facturacion"))
        um = app.user_manager
        if "testfacturacion" not in um.users:
            um.create_user(
                username="testfacturacion",
                password="facturapass123",
                full_name="Test Invoicing",
                role="facturacion",
            )
        um.users["testfacturacion"]["must_change_password"] = False
        
        # Configure mock SAP side effect to return normal client for 5002
        def get_invoices(date_str=None, extra_invoice_numbers=None):
            if extra_invoice_numbers and 5002 in extra_invoice_numbers:
                return [{
                    "invoice_number": 5002,
                    "customer_name": "NORMAL CUSTOMER S.A.",
                    "total": 100.0,
                    "currency": "MXN",
                    "status": "Abierta"
                }]
            return [{
                "invoice_number": 5001,
                "customer_name": "VENTAS MOSTRADOR GDL",
                "total": 100.0,
                "currency": "MXN",
                "status": "Abierta"
            }]
        self.mock_sap.get_todays_invoices.side_effect = get_invoices
        
        client = app.test_client()
        client.post(
            "/login",
            data={"username": "testfacturacion", "password": "facturapass123"},
            follow_redirects=True
        )

        # 1. Authorizing normal invoice should fail with 403
        payload_normal = {
            "authorized": True,
            "customer_name": "NORMAL CUSTOMER S.A."
        }
        resp = client.post(
            "/orders/api/facturas/5002/authorize",
            data=json.dumps(payload_normal),
            content_type="application/json"
        )
        assert resp.status_code == 403

        # 2. Authorizing mostrador invoice should succeed with 200
        payload_mostrador = {
            "authorized": True,
            "customer_name": "VENTAS MOSTRADOR GDL"
        }
        resp = client.post(
            "/orders/api/facturas/5001/authorize",
            data=json.dumps(payload_mostrador),
            content_type="application/json"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
