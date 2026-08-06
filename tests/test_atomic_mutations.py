"""
Unit tests for P1-02 Atomic Order State Mutations (update_order_fields)
"""

import datetime
import pytest
from unittest.mock import MagicMock, patch


def test_update_order_fields_updates_in_memory_and_saves(app):
    """Verify that update_order_fields merges fields and calls _save_order when save=True."""
    osm = app.order_status_mgr
    # Ensure sample order exists
    osm.orders["5001"] = {"order_id": "5001", "status": "Pendiente", "last_updated": "2026-01-01T00:00:00"}

    with patch.object(osm, "_save_order", return_value=True) as mock_save:
        res = osm.update_order_fields("5001", {"delivery_number": "DEL-9999", "carrier": "DHL"}, save=True)
        assert res is True
        mock_save.assert_called_once_with("5001")

        order = osm.get_order("5001")
        assert order["delivery_number"] == "DEL-9999"
        assert order["carrier"] == "DHL"
        assert "last_updated" in order


def test_update_order_fields_without_immediate_save(app):
    """Verify that save=False updates in-memory dictionary without immediate _save_order call."""
    osm = app.order_status_mgr
    osm.orders["5001"] = {"order_id": "5001", "status": "Pendiente"}

    with patch.object(osm, "_save_order") as mock_save:
        res = osm.update_order_fields("5001", {"factura_number": "FAC-8888"}, save=False)
        assert res is True
        mock_save.assert_not_called()

        order = osm.get_order("5001")
        assert order["factura_number"] == "FAC-8888"


def test_update_order_fields_non_existent_order(app):
    """Verify that updating a non-existent order returns False and logs warning."""
    osm = app.order_status_mgr
    res = osm.update_order_fields("9999999", {"status": "Cancelled"})
    assert res is False
