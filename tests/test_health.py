"""
Health & boot tests — verify the app starts and responds without
any external infrastructure (SAP / SQL Server).
"""


class TestHealthEndpoint:
    """Tests for GET /health"""

    def test_health_returns_200(self, client):
        response = client.get('/health')
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        response = client.get('/health')
        data = response.get_json()
        assert data is not None
        assert 'status' in data
        assert data['status'] == 'ok'

    def test_health_contains_app_name(self, client):
        data = client.get('/health').get_json()
        assert data['app'] == 'Open-OMS'

    def test_health_reports_sap_availability(self, client):
        data = client.get('/health').get_json()
        assert 'sap_available' in data

    def test_health_reports_order_count(self, client):
        data = client.get('/health').get_json()
        assert 'orders_loaded' in data
        assert isinstance(data['orders_loaded'], int)


class TestAppBoot:
    """Verify the application boots correctly in test mode."""

    def test_app_is_testing(self, app):
        assert app.config['TESTING'] is True

    def test_csrf_disabled_in_testing(self, app):
        assert app.config.get('WTF_CSRF_ENABLED') is False

    def test_app_has_order_manager(self, app):
        assert hasattr(app, 'order_status_mgr')
        assert app.order_status_mgr is not None

    def test_app_has_user_manager(self, app):
        assert hasattr(app, 'user_manager')
        assert app.user_manager is not None

    def test_seed_data_loaded(self, app):
        """Conftest seeds 2 orders — verify they are present."""
        orders = app.order_status_mgr.orders
        assert len(orders) >= 2
        assert '10001' in orders
        assert '10002' in orders

