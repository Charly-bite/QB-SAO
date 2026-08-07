import pytest
import json
from unittest.mock import MagicMock
from core.factura_metadata_manager import FacturaMetadataManager

def test_metadata_manager_save_and_get_observaciones(tmp_path):
    json_path = str(tmp_path / "factura_metadata.json")
    mgr = FacturaMetadataManager(db_path=json_path, db_client=MagicMock(engine=None))
    
    # Save note for invoice 90001
    mgr.save_observaciones(90001, "Entregar en puerta principal")
    
    obs_map = mgr.get_observaciones()
    assert obs_map.get(90001) == "Entregar en puerta principal"

def test_toggle_observaciones_without_local_order(auth_client, app):
    """Verify POST /api/facturas/<id>/toggle with field='observaciones' succeeds for SAP facturas without local orders."""
    invoice_num = 88888
    
    response = auth_client.post(
        f"/orders/api/facturas/{invoice_num}/toggle",
        json={"field": "observaciones", "value": "Nota de prueba SAP"}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert data.get("success") is True
    
    # Verify metadata manager saved it
    mgr = getattr(app, "factura_metadata_mgr", None)
    if mgr:
        obs = mgr.get_observaciones()
        assert obs.get(invoice_num) == "Nota de prueba SAP"

def test_get_facturas_by_date_includes_saved_notes(auth_client, app, monkeypatch):
    """Verify GET /api/facturas/by-date hydrates saved observaciones from metadata."""
    invoice_num = 77777
    mgr = getattr(app, "factura_metadata_mgr", None)
    if mgr:
        mgr.save_observaciones(invoice_num, "Observacion especial")

    sap_mock = MagicMock()
    sap_mock.connected = True
    invoices_list = [
        {
            "invoice_number": invoice_num,
            "invoice_date": "2026-08-07T00:00:00",
            "customer_name": "CLIENTE DE PRUEBA",
            "card_code": "C001",
            "total": 1500.0,
            "currency": "MXN",
            "status": "Abierta",
            "payment_terms": "CONTADO",
            "warehouse": "GDL",
            "shipping_type": "LOCAL"
        }
    ]
    sap_mock.get_todays_invoices.return_value = invoices_list
    sap_mock.get_invoices_by_date_range.return_value = invoices_list
    monkeypatch.setattr(app, "sap_connector", sap_mock)

    response = auth_client.get("/orders/api/facturas?date=07/08/2026")
    assert response.status_code == 200
    data = response.get_json()
    assert "invoices" in data
    found = next((inv for inv in data["invoices"] if inv["invoice_number"] == invoice_num), None)
    assert found is not None
    assert found.get("observaciones") == "Observacion especial"

def test_metadata_manager_save_and_get_credito_notes_unauthorized(tmp_path):
    """Verify save_credito_notes is retrieved in get_credito_authorizations even when unauthorized."""
    json_path = str(tmp_path / "factura_metadata.json")
    mgr = FacturaMetadataManager(db_path=json_path, db_client=MagicMock(engine=None))
    
    mgr.save_credito_notes(90002, "Nota Credito PRUEBA")
    
    auths = mgr.get_credito_authorizations()
    assert 90002 in auths
    assert auths[90002]["credito_notes"] == "Nota Credito PRUEBA"

def test_api_credito_notes_persistence(auth_client, app):
    """Verify POST /api/facturas/<id>/credito-notes persists credit notes."""
    invoice_num = 66666
    
    response = auth_client.post(
        f"/orders/api/facturas/{invoice_num}/credito-notes",
        json={"notes": "Nota de Crédito via API", "client_id": "test_client"}
    )
    
    assert response.status_code == 200
    data = response.get_json()
    assert data.get("success") is True
    assert data.get("notes") == "Nota de Crédito via API"
    
    mgr = getattr(app, "factura_metadata_mgr", None)
    if mgr:
        auths = mgr.get_credito_authorizations()
        assert auths.get(invoice_num, {}).get("credito_notes") == "Nota de Crédito via API"

def test_reyesm_can_sign_almacen_signature(app):
    """Verify user ReyesM can post a signature to the almacen area."""
    with app.test_client() as client:
        # Create or fetch ReyesM user
        um = app.user_manager
        if "reyesm" not in um.users:
            um.create_user(
                username="reyesm",
                password="reyespass123",
                full_name="Reyes Martinez",
                role="viewer"
            )
        
        # Set a signature_path on ReyesM
        um.users["reyesm"]["signature_path"] = "images/signatures/reyesm_signature.png"
        
        # Login as ReyesM
        client.post("/login", data={"username": "reyesm", "password": "reyespass123"})
        
        response = client.post(
            "/orders/api/relaciones/RE-070826/signatures",
            json={"area": "almacen", "action": "sign"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data.get("success") is True
        assert data.get("signatures", {}).get("almacen", {}).get("signature_path") == "images/signatures/reyesm_signature.png"

def test_metadata_manager_save_and_get_almacen_notes(tmp_path):
    """Verify save_almacen_notes and get_almacen_notes in FacturaMetadataManager."""
    json_path = str(tmp_path / "factura_metadata.json")
    mgr = FacturaMetadataManager(db_path=json_path, db_client=MagicMock(engine=None))
    
    mgr.save_almacen_notes(90003, "Empacado con emplaye especial")
    notes_map = mgr.get_almacen_notes()
    assert notes_map.get(90003) == "Empacado con emplaye especial"

def test_api_almacen_notes_persistence(app):
    """Verify POST /api/facturas/<id>/almacen-notes persists warehouse notes for ReyesM."""
    with app.test_client() as client:
        um = app.user_manager
        if "reyesm" not in um.users:
            um.create_user(
                username="reyesm",
                password="reyespass123",
                full_name="Reyes Martinez",
                role="viewer"
            )
        client.post("/login", data={"username": "reyesm", "password": "reyespass123"})
        
        response = client.post(
            "/orders/api/facturas/55555/almacen-notes",
            json={"notes": "Nota de Almacen via API", "client_id": "test_client"}
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data.get("success") is True
        assert data.get("notes") == "Nota de Almacen via API"
        
        mgr = getattr(app, "factura_metadata_mgr", None)
        if mgr:
            notes = mgr.get_almacen_notes()
            assert notes.get(55555) == "Nota de Almacen via API"
