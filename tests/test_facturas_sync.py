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
