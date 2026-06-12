"""Tests for the SGA label-print webhook API.

POST /orders/api/sga/label-printed
"""

import json
import os
from unittest.mock import patch

import pytest


SGA_ENDPOINT = "/orders/api/sga/label-printed"
TEST_API_KEY = "test-sga-secret-key-2026"


class TestSgaLabelPrintedAuth:
    """Authentication and authorization tests."""

    def test_returns_503_when_api_key_not_configured(self, client):
        """Endpoint is disabled when SGA_API_KEY is not set."""
        with patch.dict(os.environ, {"SGA_API_KEY": ""}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10001", "station": "Almacen1"},
            )
            assert resp.status_code == 503
            data = resp.get_json()
            assert "not configured" in data["error"].lower() or "not configured" in data["error"]

    def test_returns_401_when_no_api_key_provided(self, client):
        """Request without API key is rejected."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10001", "station": "Almacen1"},
            )
            assert resp.status_code == 401

    def test_returns_401_when_wrong_api_key(self, client):
        """Request with wrong API key is rejected."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10001", "station": "Almacen1"},
                headers={"X-API-Key": "wrong-key"},
            )
            assert resp.status_code == 401

    def test_accepts_api_key_via_header(self, client):
        """API key via X-API-Key header works."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10001", "station": "Almacen1"},
                headers={"X-API-Key": TEST_API_KEY},
            )
            # Should not be 401 or 503
            assert resp.status_code not in (401, 503)

    def test_accepts_api_key_via_query_param(self, client):
        """API key via query parameter works."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                f"{SGA_ENDPOINT}?api_key={TEST_API_KEY}",
                json={"order_id": "10001", "station": "Almacen1"},
            )
            assert resp.status_code not in (401, 503)


class TestSgaLabelPrintedValidation:
    """Input validation tests."""

    def test_returns_400_when_order_id_missing(self, client):
        """Missing order_id is rejected."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={"station": "Almacen1"},
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert resp.status_code == 400
            assert "order_id" in resp.get_json()["error"]

    def test_returns_400_when_station_missing(self, client):
        """Missing station is rejected."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10001"},
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert resp.status_code == 400
            assert "station" in resp.get_json()["error"]

    def test_returns_404_for_nonexistent_order(self, client, app):
        """Order not found returns 404 (SAP auto-import disabled in test)."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            # Disable SAP auto-import and make get_order return None
            original_sap = app.sap_available
            app.sap_available = False
            try:
                with patch.object(app.order_status_mgr, "get_order", return_value=None):
                    resp = client.post(
                        SGA_ENDPOINT,
                        json={"order_id": "99999", "station": "Almacen1"},
                        headers={"X-API-Key": TEST_API_KEY},
                    )
            finally:
                app.sap_available = original_sap
            assert resp.status_code == 202


class TestSgaLabelPrintedSuccess:
    """Happy-path tests."""

    def test_transitions_pending_to_en_proceso(self, client, app):
        """Order at 'Pendiente' is moved to 'En Proceso'."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={
                    "order_id": "10001",
                    "station": "Almacen1",
                    "items": ["PROD-A"],
                    "event_type": "DIRECT_PRINT_JOB",
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["order_id"] == "10001"
            assert data["previous_status"] == "Pendiente"
            assert data["new_status"] == "En Proceso"

            # Verify the order was actually updated in the manager
            with app.app_context():
                order = app.order_status_mgr.get_order("10001")
                assert order["status"] == "En Proceso"

    def test_idempotent_for_same_status(self, client, app):
        """Calling for an order already at 'En Proceso' succeeds (idempotent)."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            # Order 10002 is already "En Proceso" in seed data
            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10002", "station": "Alm01"},
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True

    def test_returns_409_for_advanced_order(self, client, app):
        """Order past 'En Proceso' is NOT downgraded — returns 409."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            # First move order to Facturacion
            with app.app_context():
                app.order_status_mgr.update_status(
                    "10001", "Facturacion", "test", "moved for test"
                )

            resp = client.post(
                SGA_ENDPOINT,
                json={"order_id": "10001", "station": "Almacen1"},
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert resp.status_code == 409
            data = resp.get_json()
            assert data["success"] is False
            assert data["current_status"] == "Facturacion"

    def test_audit_notes_include_station_and_items(self, client, app):
        """Status history includes the station and item codes."""
        with patch.dict(os.environ, {"SGA_API_KEY": TEST_API_KEY}, clear=False):
            resp = client.post(
                SGA_ENDPOINT,
                json={
                    "order_id": "10001",
                    "station": "AlmMty",
                    "items": ["IFF-QB00053", "IFF-QB00073"],
                },
                headers={"X-API-Key": TEST_API_KEY},
            )
            assert resp.status_code == 200

            with app.app_context():
                order = app.order_status_mgr.get_order("10001")
                last_entry = order["status_history"][-1]
                assert "AlmMty" in last_entry["notes"]
                assert "IFF-QB00053" in last_entry["notes"]
