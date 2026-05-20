"""
Full-coverage tests for routes.orders — covers all SAP-dependent routes,
SSE pub/sub, weather proxy, and edge cases.
"""

import json
import os
import queue
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# SSE / Pub-Sub
# ---------------------------------------------------------------------------


class TestPublishEvent:
    def test_broadcast_to_subscribers(self, app):
        from routes.orders import _publish_event, _SUBSCRIBERS

        q = queue.Queue()
        _SUBSCRIBERS.append(q)
        try:
            _publish_event({"type": "test"})
            assert not q.empty()
            event = q.get_nowait()
            assert event["type"] == "test"
        finally:
            _SUBSCRIBERS.remove(q)

    def test_handles_full_queue(self, app):
        from routes.orders import _publish_event, _SUBSCRIBERS

        q = queue.Queue(maxsize=1)
        q.put({"old": True})  # Fill it
        _SUBSCRIBERS.append(q)
        try:
            _publish_event({"type": "new"})  # Should not raise
        finally:
            _SUBSCRIBERS.remove(q)


class TestStreamEndpoint:
    def test_stream_returns_event_stream(self, app):
        with app.test_request_context():
            # Token not set → open access
            with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
                with patch("routes.orders.Response") as mock_resp:
                    mock_resp.return_value = app.response_class(
                        "mocked", content_type="text/event-stream"
                    )
                    
                    client = app.test_client()
                    resp = client.get("/orders/stream")
                    
                    assert resp.content_type.startswith("text/event-stream")
                    mock_resp.assert_called_once()
                    assert mock_resp.call_args[1].get("mimetype") == "text/event-stream"


# ---------------------------------------------------------------------------
# Monitor token decorator
# ---------------------------------------------------------------------------


class TestRequireMonitorToken:
    def test_no_token_required(self, app):
        """When MONITOR_TOKEN is not set, access is open."""
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            client = app.test_client()
            resp = client.get("/orders/api/public/active")
            assert resp.status_code == 200

    def test_valid_token(self, app):
        with patch.dict(os.environ, {"MONITOR_TOKEN": "secret123"}, clear=False):
            client = app.test_client()
            resp = client.get("/orders/api/public/active?token=secret123")
            assert resp.status_code == 200

    def test_invalid_token(self, app):
        with patch.dict(os.environ, {"MONITOR_TOKEN": "secret123"}, clear=False):
            client = app.test_client()
            resp = client.get("/orders/api/public/active?token=wrong")
            assert resp.status_code == 401

    def test_token_in_header(self, app):
        with patch.dict(os.environ, {"MONITOR_TOKEN": "hdr_token"}, clear=False):
            client = app.test_client()
            resp = client.get(
                "/orders/api/public/active",
                headers={"X-Monitor-Token": "hdr_token"},
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# import_from_sap route
# ---------------------------------------------------------------------------


class TestImportFromSap:
    def test_sap_unavailable(self, auth_client, app):
        app.sap_available = False
        resp = auth_client.post(
            "/orders/import-sap",
            data=json.dumps({"order_number": "100"}),
            content_type="application/json",
        )
        assert resp.status_code == 503
        app.sap_available = True

    def test_missing_order_number(self, auth_client, app):
        app.sap_available = True
        resp = auth_client.post(
            "/orders/import-sap",
            data=json.dumps({"order_number": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_success(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_order_details.return_value = {
            "header": {
                "order_number": 999,
                "customer_code": "C001",
                "customer_name": "Cust",
                "order_date": "2026-01-01",
                "delivery_date": "2026-01-10",
                "total_value": 5000,
                "currency": "MXN",
                "sap_status": "Abierto",
                "factura_number": None,
                "creator_name": "Creator",
                "updater_name": "Updater",
            },
            "items": [],
        }
        app.sap_connector = mock_sap
        resp = auth_client.post(
            "/orders/import-sap",
            data=json.dumps({"order_number": "999"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_order_not_found_in_sap(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_order_details.return_value = None
        app.sap_connector = mock_sap
        resp = auth_client.post(
            "/orders/import-sap",
            data=json.dumps({"order_number": "88888"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_sap_exception(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_order_details.side_effect = Exception("SAP down")
        app.sap_connector = mock_sap
        resp = auth_client.post(
            "/orders/import-sap",
            data=json.dumps({"order_number": "100"}),
            content_type="application/json",
        )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# label-printed route
# ---------------------------------------------------------------------------


class TestLabelPrinted:
    def test_no_permission(self, viewer_client, app):
        resp = viewer_client.post("/orders/10001/label-printed")
        assert resp.status_code == 403

    def test_order_not_found(self, auth_client, app):
        resp = auth_client.post("/orders/99999/label-printed")
        assert resp.status_code == 404

    def test_success(self, auth_client, app):
        resp = auth_client.post("/orders/10001/label-printed")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


# ---------------------------------------------------------------------------
# load-recent-sap route
# ---------------------------------------------------------------------------


class TestLoadRecentFromSap:
    def _make_sap_order(self, num, sap_status="Abierto"):
        return {
            "header": {
                "order_number": num,
                "customer_code": "C1",
                "customer_name": "Customer",
                "order_date": "2026-01-01",
                "delivery_date": "2026-01-10",
                "total_value": 1000,
                "currency": "MXN",
                "sap_status": sap_status,
                "factura_number": None,
                "creator_name": "Creator",
                "updater_name": "Updater",
            },
            "items": [],
        }

    def test_sap_unavailable(self, auth_client, app):
        app.sap_available = False
        resp = auth_client.post("/orders/load-recent-sap", data=json.dumps({}), content_type="application/json")
        assert resp.status_code == 503
        app.sap_available = True

    def test_no_permissions(self, viewer_client, app):
        app.sap_available = True
        resp = viewer_client.post("/orders/load-recent-sap", data=json.dumps({}), content_type="application/json")
        assert resp.status_code == 403

    def test_success_new_and_existing(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001),  # Exists
            self._make_sap_order(20001),  # New
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post(
            "/orders/load-recent-sap",
            data=json.dumps({"limit": 10}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_sap_status_cerrado(self, auth_client, app):
        """When SAP status is Cerrado and local is Pendiente → auto-transition."""
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cerrado"),
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post(
            "/orders/load-recent-sap",
            data=json.dumps({"limit": 5}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_sap_status_cancelado(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cancelado"),
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post(
            "/orders/load-recent-sap",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_exception(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.side_effect = Exception("Boom")
        app.sap_connector = mock_sap

        resp = auth_client.post(
            "/orders/load-recent-sap",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 500

    def test_skip_invalid_order_data(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [None, {"no_header": True}]
        app.sap_connector = mock_sap

        resp = auth_client.post(
            "/orders/load-recent-sap",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# sync-sap route
# ---------------------------------------------------------------------------


class TestSyncSap:
    def test_sap_unavailable(self, auth_client, app):
        app.sap_available = False
        resp = auth_client.post("/orders/sync-sap")
        assert resp.status_code == 503
        app.sap_available = True

    def test_no_permissions(self, viewer_client, app):
        app.sap_available = True
        resp = viewer_client.post("/orders/sync-sap")
        assert resp.status_code == 403

    def test_no_orders(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        app.sap_connector = mock_sap
        # Empty order manager
        app.order_status_mgr.orders = {}

        resp = auth_client.post("/orders/sync-sap")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0

    def test_batch_sync_with_status_change(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_orders_status_batch.return_value = {
            10001: {
                "sap_status": "Cerrado",
                "doc_status": "C",
                "canceled": "N",
                "updater_name": "SAP User",
                "customer_name": "Cust",
            }
        }
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/sync-sap")
        assert resp.status_code == 200

    def test_exception(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_orders_status_batch.side_effect = Exception("SAP error")
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/sync-sap")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# visor/sync route
# ---------------------------------------------------------------------------


class TestVisorSync:
    def _make_sap_order(self, num, sap_status="Abierto", factura=None):
        return {
            "header": {
                "order_number": num,
                "customer_code": "C1",
                "customer_name": "Customer",
                "order_date": "2026-01-01",
                "delivery_date": "2026-01-10",
                "total_value": 1000,
                "currency": "MXN",
                "sap_status": sap_status,
                "factura_number": factura,
                "updater_name": "Updater",
            },
            "items": [],
        }

    def test_sap_unavailable(self, auth_client, app):
        app.sap_available = False
        resp = auth_client.post("/orders/visor/sync")
        assert resp.status_code == 503
        app.sap_available = True

    def test_success_with_updates(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cerrado"),
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/visor/sync")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_new_order_found(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(30001),
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/visor/sync")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_cancelado_transition(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cancelado"),
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/visor/sync")
        assert resp.status_code == 200

    def test_factura_sync(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, factura="F-5001"),
        ]
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/visor/sync")
        assert resp.status_code == 200

    def test_exception_returns_200(self, auth_client, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.side_effect = Exception("Visor error")
        app.sap_connector = mock_sap

        resp = auth_client.post("/orders/visor/sync")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is False


# ---------------------------------------------------------------------------
# Seller/monitor API
# ---------------------------------------------------------------------------


class TestApiSellerOrders:
    def test_seller_filtered(self, seller_client, app):
        resp = seller_client.get("/orders/api/seller/orders")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "orders" in data
        assert data["can_see_all"] is False

    def test_seller_no_sap_name(self, app):
        """Seller with no sap_seller_name → empty result."""
        client = app.test_client()
        with app.app_context():
            um = app.user_manager
            if "nosap" not in um.users:
                um.create_user(
                    username="nosap", password="nosappass1",
                    full_name="No SAP", role="seller",
                    sap_seller_name="",
                )
            client.post("/login", data={"username": "nosap", "password": "nosappass1"}, follow_redirects=True)

        resp = client.get("/orders/api/seller/orders")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["orders"] == []

    def test_manager_sees_all(self, sell_manager_client, app):
        resp = sell_manager_client.get("/orders/api/seller/orders")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["can_see_all"] is True

    def test_manager_with_seller_filter(self, sell_manager_client, app):
        resp = sell_manager_client.get("/orders/api/seller/orders?seller=system")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["can_see_all"] is True


# ---------------------------------------------------------------------------
# Public API sync
# ---------------------------------------------------------------------------


class TestPublicApiSync:
    def _make_sap_order(self, num, sap_status="Abierto", factura=None):
        return {
            "header": {
                "order_number": num,
                "customer_code": "C1",
                "customer_name": "Cust",
                "order_date": "2026-01-01",
                "delivery_date": "2026-01-10",
                "total_value": 1000,
                "currency": "MXN",
                "sap_status": sap_status,
                "factura_number": factura,
                "updater_name": "Updater",
            },
            "items": [],
        }

    def test_sap_unavailable(self, app):
        app.sap_available = False
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.post("/orders/api/public/sync")
        assert resp.status_code == 503
        app.sap_available = True

    def test_success(self, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(40001),
        ]
        app.sap_connector = mock_sap
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.post("/orders/api/public/sync")
        assert resp.status_code == 200

    def test_cerrado_transition(self, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cerrado"),
        ]
        app.sap_connector = mock_sap
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.post("/orders/api/public/sync")
        assert resp.status_code == 200

    def test_cancelado_transition(self, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cancelado"),
        ]
        app.sap_connector = mock_sap
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.post("/orders/api/public/sync")
        assert resp.status_code == 200

    def test_factura_update(self, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, factura="INV-100"),
        ]
        app.sap_connector = mock_sap
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.post("/orders/api/public/sync")
        assert resp.status_code == 200

    def test_exception(self, app):
        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.side_effect = Exception("Boom")
        app.sap_connector = mock_sap
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.post("/orders/api/public/sync")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Public active API — limit clamping
# ---------------------------------------------------------------------------


class TestPublicActiveApi:
    def test_default_limit(self, app):
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.get("/orders/api/public/active")
        assert resp.status_code == 200

    def test_invalid_limit(self, app):
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.get("/orders/api/public/active?limit=abc")
        assert resp.status_code == 200

    def test_large_limit_clamped(self, app):
        client = app.test_client()
        with patch.dict(os.environ, {"MONITOR_TOKEN": ""}, clear=False):
            resp = client.get("/orders/api/public/active?limit=9999")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Refresh route (throttled SAP sync)
# ---------------------------------------------------------------------------


class TestApiRefreshOrders:
    def _make_sap_order(self, num, sap_status="Abierto", factura=None):
        return {
            "header": {
                "order_number": num,
                "customer_code": "C1",
                "customer_name": "Cust",
                "order_date": "2026-01-01",
                "delivery_date": "2026-01-10",
                "total_value": 1000,
                "currency": "MXN",
                "sap_status": sap_status,
                "factura_number": factura,
                "updater_name": "Updater",
            },
            "items": [],
        }

    def test_no_sap(self, auth_client, app):
        """When SAP is not available, should still return order list."""
        app.sap_available = False
        resp = auth_client.get("/orders/api/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sap_synced"] is False
        app.sap_available = True

    def test_with_sap_sync(self, auth_client, app):
        import routes.orders as mod
        mod._last_sap_sync = 0  # Force sync

        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.return_value = [
            self._make_sap_order(10001, sap_status="Cerrado", factura="F-100"),
            self._make_sap_order(50001),  # New order
        ]
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sap_synced"] is True

    def test_sap_sync_throttled(self, auth_client, app):
        import routes.orders as mod
        mod._last_sap_sync = time.time()  # Just synced

        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sap_synced"] is False

    def test_sap_sync_exception(self, auth_client, app):
        import routes.orders as mod
        mod._last_sap_sync = 0

        app.sap_available = True
        mock_sap = MagicMock()
        mock_sap.connected = True
        mock_sap.get_recent_orders.side_effect = Exception("SAP down")
        app.sap_connector = mock_sap

        resp = auth_client.get("/orders/api/refresh")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["sap_synced"] is False

    def test_with_filters(self, auth_client, app):
        app.sap_available = False
        resp = auth_client.get("/orders/api/refresh?status=Pendiente&search=10001")
        assert resp.status_code == 200
        app.sap_available = True


# ---------------------------------------------------------------------------
# Weather proxy
# ---------------------------------------------------------------------------


class TestWeatherProxy:
    def test_no_api_key(self, app):
        client = app.test_client()
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": ""}, clear=False):
            resp = client.get("/orders/api/public/weather")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["temp"] is None

    def test_fresh_fetch_success(self, app):
        import routes.orders as mod
        mod._weather_cache = {"data": None, "timestamp": 0}

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "main": {"temp": 25.3, "feels_like": 26.0, "humidity": 60},
            "weather": [{"main": "Clear", "id": 800, "description": "cielo despejado", "icon": "01d"}],
            "wind": {"speed": 3.5},
            "clouds": {"all": 10},
            "sys": {"sunrise": 1700000000, "sunset": 1700040000},
            "name": "Guadalajara",
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        client = app.test_client()
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": "testkey123"}, clear=False):
            with patch("routes.orders.urllib.request.urlopen", return_value=mock_response):
                resp = client.get("/orders/api/public/weather")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["temp"] == 25
        assert data["city"] == "Guadalajara"

    def test_cached_response(self, app):
        import routes.orders as mod
        cached = {
            "temp": 30, "condition": "Clouds", "condition_id": 802,
            "description": "nubes", "city": "Guadalajara", "clouds": 50,
        }
        mod._weather_cache = {"data": cached, "timestamp": time.time(), "city": "guadalajara,mx"}

        client = app.test_client()
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": "key"}, clear=False):
            resp = client.get("/orders/api/public/weather?city=Guadalajara,MX")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["temp"] == 30

    def test_api_error_with_stale_cache(self, app):
        import routes.orders as mod
        stale = {"temp": 20, "condition": "Rain", "condition_id": 500, "description": "lluvia", "city": "GDL", "clouds": 80}
        mod._weather_cache = {"data": stale, "timestamp": 0, "city": "guadalajara,mx"}

        client = app.test_client()
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": "key"}, clear=False):
            with patch("routes.orders.urllib.request.urlopen", side_effect=Exception("API error")):
                resp = client.get("/orders/api/public/weather?city=Guadalajara,MX")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["temp"] == 20  # Stale cache returned

    def test_api_error_no_cache(self, app):
        import routes.orders as mod
        mod._weather_cache = {"data": None, "timestamp": 0}

        client = app.test_client()
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": "key"}, clear=False):
            with patch("routes.orders.urllib.request.urlopen", side_effect=Exception("API error")):
                resp = client.get("/orders/api/public/weather")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["temp"] is None


# ---------------------------------------------------------------------------
# Status update edge cases
# ---------------------------------------------------------------------------


class TestUpdateStatusEdgeCases:
    def test_case_insensitive_match(self, auth_client, app):
        """Status matched case-insensitively."""
        resp = auth_client.post(
            "/orders/10001/status",
            data=json.dumps({"status": "pendiente"}),  # lowercase
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_enum_name_fallback(self, auth_client, app):
        """Status matched by enum member name (e.g. 'READY')."""
        resp = auth_client.post(
            "/orders/10001/status",
            data=json.dumps({"status": "READY"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_completely_invalid_status(self, auth_client, app):
        resp = auth_client.post(
            "/orders/10001/status",
            data=json.dumps({"status": "TotallyFake"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_alias_status(self, auth_client, app):
        """Status alias like 'Facturado' → 'Facturacion'."""
        resp = auth_client.post(
            "/orders/10001/status",
            data=json.dumps({"status": "Facturado"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
