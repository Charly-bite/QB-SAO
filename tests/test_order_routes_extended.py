"""
Extended order route tests — covers visor, public API, label printing,
API list/refresh, monitor token, and operator role gating.
"""
import json
import os
from unittest.mock import patch


class TestVisorRoute:
    """GET /orders/visor — seller self-service dashboard."""

    def test_visor_renders_for_admin(self, auth_client):
        response = auth_client.get('/orders/visor')
        assert response.status_code == 200

    def test_visor_renders_for_operator(self, operator_client):
        response = operator_client.get('/orders/visor')
        assert response.status_code == 200

    def test_visor_renders_for_seller(self, seller_client):
        response = seller_client.get('/orders/visor')
        assert response.status_code == 200

    def test_visor_requires_login(self, client):
        response = client.get('/orders/visor', follow_redirects=False)
        assert response.status_code in (302, 303)


class TestApiActiveOrders:
    """GET /orders/api/active — JSON active order list."""

    def test_returns_json_for_admin(self, auth_client):
        response = auth_client.get('/orders/api/active')
        assert response.status_code == 200
        data = response.get_json()
        assert 'orders' in data
        assert 'stats' in data
        assert 'generated_at' in data

    def test_stats_contain_expected_keys(self, auth_client):
        data = auth_client.get('/orders/api/active').get_json()
        for key in ('total_active', 'pending', 'picking', 'ready', 'shipped'):
            assert key in data['stats']

    def test_requires_login(self, client):
        response = client.get('/orders/api/active', follow_redirects=False)
        assert response.status_code in (302, 401)


class TestApiListOrders:
    """GET /orders/api/list — paginated order list JSON."""

    def test_returns_all_orders(self, auth_client):
        data = auth_client.get('/orders/api/list').get_json()
        assert 'orders' in data
        assert 'status_counts' in data
        assert len(data['orders']) >= 2  # seed data

    def test_filter_by_status(self, auth_client):
        data = auth_client.get('/orders/api/list?status=Pendiente').get_json()
        for order in data['orders']:
            assert order['status'] == 'Pendiente'

    def test_search_filter(self, auth_client):
        data = auth_client.get('/orders/api/list?search=Prueba').get_json()
        assert any('Prueba' in o.get('customer_name', '') for o in data['orders'])

    def test_requires_login(self, client):
        response = client.get('/orders/api/list', follow_redirects=False)
        assert response.status_code in (302, 401)


class TestApiRefreshOrders:
    """GET /orders/api/refresh — reconcile + return full list."""

    def test_returns_order_data(self, auth_client):
        data = auth_client.get('/orders/api/refresh').get_json()
        assert 'orders' in data
        assert 'status_counts' in data
        assert 'reconciled' in data
        assert 'sap_synced' in data

    def test_filter_and_search(self, auth_client):
        data = auth_client.get('/orders/api/refresh?status=Pendiente&search=10001').get_json()
        assert 'orders' in data

    def test_requires_login(self, client):
        response = client.get('/orders/api/refresh', follow_redirects=False)
        assert response.status_code in (302, 401)


class TestPublicApiActive:
    """GET /orders/api/public/active — token-protected public endpoint."""

    def test_works_without_token_when_not_configured(self, client):
        """When MONITOR_TOKEN env var is empty/unset, endpoint is open."""
        with patch.dict(os.environ, {'MONITOR_TOKEN': ''}, clear=False):
            response = client.get('/orders/api/public/active')
            assert response.status_code == 200
            data = response.get_json()
            assert 'orders' in data
            assert 'stats' in data

    def test_rejects_wrong_token(self, client):
        """When MONITOR_TOKEN is set, a wrong token returns 401."""
        with patch.dict(os.environ, {'MONITOR_TOKEN': 'correct-secret'}):
            response = client.get('/orders/api/public/active?token=wrong')
            assert response.status_code == 401

    def test_accepts_valid_token_in_query(self, client):
        """Valid token in query param grants access."""
        with patch.dict(os.environ, {'MONITOR_TOKEN': 'my-token'}):
            response = client.get('/orders/api/public/active?token=my-token')
            assert response.status_code == 200

    def test_accepts_valid_token_in_header(self, client):
        """Valid token in X-Monitor-Token header grants access."""
        with patch.dict(os.environ, {'MONITOR_TOKEN': 'my-token'}):
            response = client.get(
                '/orders/api/public/active',
                headers={'X-Monitor-Token': 'my-token'},
            )
            assert response.status_code == 200

    def test_limit_parameter(self, client):
        """The limit parameter should be respected."""
        with patch.dict(os.environ, {'MONITOR_TOKEN': ''}, clear=False):
            response = client.get('/orders/api/public/active?limit=1')
            assert response.status_code == 200
            data = response.get_json()
            assert len(data['orders']) <= 1


class TestPublicApiWeather:
    """GET /orders/api/public/weather — weather proxy."""

    def test_returns_fallback_without_api_key(self, client):
        """Without OPENWEATHER_API_KEY, returns a placeholder response."""
        with patch.dict(os.environ, {'OPENWEATHER_API_KEY': ''}, clear=False):
            os.environ.pop('OPENWEATHER_API_KEY', None)
            response = client.get('/orders/api/public/weather')
            assert response.status_code == 200
            data = response.get_json()
            assert data['temp'] is None
            assert 'condition' in data


class TestLabelPrinted:
    """POST /orders/<id>/label-printed — transitions status."""

    def test_operator_can_mark_label_printed(self, operator_client, app):
        response = operator_client.post('/orders/10001/label-printed')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify status changed to "En Proceso"
        with app.app_context():
            order = app.order_status_mgr.get_order('10001')
            assert order['status'] == 'En Proceso'

    def test_viewer_cannot_mark_label_printed(self, viewer_client):
        response = viewer_client.post('/orders/10001/label-printed')
        assert response.status_code == 403

    def test_missing_order_returns_404(self, operator_client):
        response = operator_client.post('/orders/99999/label-printed')
        assert response.status_code == 404


class TestOperatorRoleGating:
    """Verify that operators CAN update status and add orders."""

    def test_operator_can_update_status(self, operator_client):
        response = operator_client.post(
            '/orders/10001/status',
            data=json.dumps({'status': 'En Proceso', 'notes': 'operator test'}),
            content_type='application/json',
        )
        assert response.status_code == 200

    def test_operator_can_add_order(self, operator_client):
        response = operator_client.post(
            '/orders/add',
            data=json.dumps({
                'order_id': '88001',
                'customer_name': 'Operator Added',
                'customer_code': 'OPR1',
            }),
            content_type='application/json',
        )
        assert response.status_code == 200

    def test_seller_cannot_update_status(self, seller_client):
        response = seller_client.post(
            '/orders/10001/status',
            data=json.dumps({'status': 'En Proceso'}),
            content_type='application/json',
        )
        assert response.status_code == 403

    def test_seller_cannot_add_order(self, seller_client):
        response = seller_client.post(
            '/orders/add',
            data=json.dumps({
                'order_id': '88002',
                'customer_name': 'Seller Nope',
            }),
            content_type='application/json',
        )
        assert response.status_code == 403


class TestSapUnavailableRoutes:
    """Routes that require SAP should return 503 when sap_available is False."""

    def test_import_sap_returns_503(self, auth_client, app):
        app.sap_available = False
        response = auth_client.post(
            '/orders/import-sap',
            data=json.dumps({'order_number': '12345'}),
            content_type='application/json',
        )
        assert response.status_code == 503

    def test_sync_sap_returns_503(self, auth_client, app):
        app.sap_available = False
        response = auth_client.post('/orders/sync-sap')
        assert response.status_code == 503


class TestErrorHandlers:
    """App-level error handlers."""

    def test_404_html_for_browser(self, auth_client):
        response = auth_client.get('/orders/nonexistent-page')
        assert response.status_code == 404

    def test_404_json_for_api(self, client):
        response = client.get(
            '/api/does-not-exist',
            headers={'Accept': 'application/json'},
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_root_redirects_to_orders(self, client):
        response = client.get('/', follow_redirects=False)
        assert response.status_code in (302, 303)

    def test_favicon_returns_image(self, client):
        response = client.get('/favicon.ico')
        # Could be 200 if the image exists, or 404 in test if missing
        assert response.status_code in (200, 404)


class TestToggleFacturaStatus:
    """POST /orders/api/facturas/<invoice_number>/toggle — toggles status."""

    def test_reyesm_can_toggle_entrega_and_rebote(self, app):
        with app.app_context():
            um = app.user_manager
            if "reyesm" not in um.users:
                um.create_user(
                    username="ReyesM",
                    password="reyespass123",
                    full_name="Reyes M",
                    role="viewer",
                )

        client = app.test_client()
        client.post(
            "/login",
            data={"username": "ReyesM", "password": "reyespass123"},
            follow_redirects=True,
        )

        with app.app_context():
            order = app.order_status_mgr.orders["10001"]
            order["factura_number"] = "10001"
            app.order_status_mgr._save_order("10001")

        response = client.post(
            "/orders/api/facturas/10001/toggle",
            data=json.dumps({"field": "entrega", "value": True}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data.get("success") is True

        response = client.post(
            "/orders/api/facturas/10001/toggle",
            data=json.dumps({"field": "rebote", "value": True}),
            content_type="application/json",
        )
        assert response.status_code == 200

        response = client.post(
            "/orders/api/facturas/10001/toggle",
            data=json.dumps({"field": "recibido", "value": True}),
            content_type="application/json",
        )
        assert response.status_code == 403

    def test_viewer_cannot_toggle_any(self, viewer_client, app):
        with app.app_context():
            order = app.order_status_mgr.orders["10001"]
            order["factura_number"] = "10001"
            app.order_status_mgr._save_order("10001")

        response = viewer_client.post(
            "/orders/api/facturas/10001/toggle",
            data=json.dumps({"field": "entrega", "value": True}),
            content_type="application/json",
        )
        assert response.status_code == 403
