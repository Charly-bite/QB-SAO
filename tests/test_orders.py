"""
Order routes tests — dashboard, detail view, status updates, manual creation.
"""
import json


class TestOrderDashboard:
    """GET /orders/ — main order list."""

    def test_dashboard_renders_for_admin(self, auth_client):
        response = auth_client.get('/orders/')
        assert response.status_code == 200

    def test_dashboard_shows_seeded_orders(self, auth_client):
        response = auth_client.get('/orders/')
        html = response.data.decode('utf-8')
        assert '10001' in html
        assert 'Cliente Prueba' in html

    def test_dashboard_filter_by_status(self, auth_client):
        response = auth_client.get('/orders/?status=Pendiente')
        assert response.status_code == 200

    def test_dashboard_search(self, auth_client):
        response = auth_client.get('/orders/?search=Prueba')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'Cliente Prueba' in html


class TestOrderDetail:
    """GET /orders/<id> — individual order view."""

    def test_detail_existing_order(self, auth_client):
        response = auth_client.get('/orders/10001')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert '10001' in html

    def test_detail_missing_order_returns_404(self, auth_client):
        response = auth_client.get('/orders/99999')
        assert response.status_code == 404


class TestStatusUpdate:
    """POST /orders/<id>/status — status transitions."""

    def test_update_status_valid(self, auth_client):
        response = auth_client.post(
            '/orders/10001/status',
            data=json.dumps({'status': 'En Proceso', 'notes': 'Test update'}),
            content_type='application/json',
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('success') is True

    def test_update_status_invalid(self, auth_client):
        response = auth_client.post(
            '/orders/10001/status',
            data=json.dumps({'status': 'Estado Inventado'}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_update_status_empty(self, auth_client):
        response = auth_client.post(
            '/orders/10001/status',
            data=json.dumps({'status': ''}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_update_status_missing_order(self, auth_client):
        response = auth_client.post(
            '/orders/99999/status',
            data=json.dumps({'status': 'Pendiente'}),
            content_type='application/json',
        )
        assert response.status_code == 404

    def test_viewer_cannot_update_status(self, viewer_client):
        response = viewer_client.post(
            '/orders/10001/status',
            data=json.dumps({'status': 'En Proceso'}),
            content_type='application/json',
        )
        assert response.status_code == 403


class TestManualOrderCreation:
    """POST /orders/add — manual order entry."""

    def test_add_order(self, auth_client, app):
        response = auth_client.post(
            '/orders/add',
            data=json.dumps({
                'order_id': '99001',
                'customer_name': 'Nuevo Cliente Test',
                'customer_code': 'CT99',
            }),
            content_type='application/json',
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data.get('success') is True

        # Verify it was persisted in memory
        with app.app_context():
            order = app.order_status_mgr.get_order('99001')
            assert order is not None
            assert order['customer_name'] == 'Nuevo Cliente Test'

    def test_add_duplicate_order_fails(self, auth_client):
        """Order 10001 already exists in seed data."""
        response = auth_client.post(
            '/orders/add',
            data=json.dumps({
                'order_id': '10001',
                'customer_name': 'Duplicado',
            }),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_add_order_missing_fields(self, auth_client):
        response = auth_client.post(
            '/orders/add',
            data=json.dumps({'order_id': ''}),
            content_type='application/json',
        )
        assert response.status_code == 400

    def test_viewer_cannot_add_order(self, viewer_client):
        response = viewer_client.post(
            '/orders/add',
            data=json.dumps({
                'order_id': '99002',
                'customer_name': 'Nope',
            }),
            content_type='application/json',
        )
        assert response.status_code == 403


class TestDeleteOrder:
    """DELETE /orders/<id>/delete — admin-only deletion."""

    def test_admin_can_delete(self, auth_client, app):
        # First create an order to delete
        auth_client.post(
            '/orders/add',
            data=json.dumps({
                'order_id': '99003',
                'customer_name': 'Para Borrar',
            }),
            content_type='application/json',
        )
        response = auth_client.delete('/orders/99003/delete')
        assert response.status_code == 200

    def test_viewer_cannot_delete(self, viewer_client):
        response = viewer_client.delete('/orders/10001/delete')
        assert response.status_code == 403

    def test_delete_missing_order(self, auth_client):
        response = auth_client.delete('/orders/99999/delete')
        assert response.status_code == 404


class TestMonitorRoute:
    """GET /orders/monitor — seller tracking panel."""

    def test_monitor_requires_login(self, client):
        response = client.get('/orders/monitor')
        assert response.status_code in (302, 401)

    def test_monitor_renders_for_admin(self, auth_client):
        response = auth_client.get('/orders/monitor')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'QB-SAO' in html

    def test_monitor_renders_for_seller(self, seller_client):
        response = seller_client.get('/orders/monitor')
        assert response.status_code == 200


class TestSellerAPI:
    """GET /orders/api/seller/orders — role-based order filtering."""

    def test_api_requires_login(self, client):
        response = client.get('/orders/api/seller/orders')
        assert response.status_code in (302, 401)

    def test_admin_sees_all_orders(self, auth_client):
        response = auth_client.get('/orders/api/seller/orders')
        assert response.status_code == 200
        data = response.get_json()
        assert data['can_see_all'] is True
        assert len(data['orders']) >= 2  # seed has 2 orders

    def test_seller_sees_only_own_orders(self, seller_client):
        """Seller with sap_seller_name='system' should see only orders
        where created_by='system' (order 10001 in seed data)."""
        response = seller_client.get('/orders/api/seller/orders')
        assert response.status_code == 200
        data = response.get_json()
        assert data['can_see_all'] is False
        # Only order 10001 has created_by='system'
        for order in data['orders']:
            assert order['created_by'].lower() == 'system'

    def test_manager_can_filter_by_seller(self, sell_manager_client):
        response = sell_manager_client.get('/orders/api/seller/orders?seller=system')
        assert response.status_code == 200
        data = response.get_json()
        assert data['can_see_all'] is True
        for order in data['orders']:
            assert order['created_by'].lower() == 'system'

    def test_api_returns_stats(self, auth_client):
        response = auth_client.get('/orders/api/seller/orders')
        data = response.get_json()
        assert 'stats' in data
        assert 'pending' in data['stats']
        assert 'in_progress' in data['stats']
        assert 'invoicing' in data['stats']

    def test_api_returns_sellers_list(self, auth_client):
        response = auth_client.get('/orders/api/seller/orders')
        data = response.get_json()
        assert 'sellers' in data
        assert isinstance(data['sellers'], list)

