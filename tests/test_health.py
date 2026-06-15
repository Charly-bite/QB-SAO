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


class TestErrorHandlers:
    """Tests for 404 and 500 error handlers in app.py."""

    def test_404_json(self, client):
        """JSON 404 for API paths."""
        resp = client.get('/api/nonexistent', headers={'Accept': 'application/json'})
        assert resp.status_code == 404

    def test_404_html(self, client):
        """HTML 404 for regular paths."""
        resp = client.get('/totally-missing-page')
        assert resp.status_code == 404

    def test_500_json(self, app):
        """JSON 500 error handler."""
        @app.route('/test-500')
        def trigger_500():
            raise RuntimeError("Test 500 error")

        app.config['TESTING'] = False
        app.config['PROPAGATE_EXCEPTIONS'] = False
        client = app.test_client()
        resp = client.get('/test-500', headers={'Accept': 'application/json'})
        assert resp.status_code == 500

    def test_500_html(self, app):
        """HTML 500 error handler."""
        @app.route('/test-500-html')
        def trigger_500_html():
            raise RuntimeError("Test 500 HTML")

        app.config['TESTING'] = False
        app.config['PROPAGATE_EXCEPTIONS'] = False
        client = app.test_client()
        resp = client.get('/test-500-html')
        assert resp.status_code == 500


class TestUserLoader:
    """Tests for the Flask-Login user_loader callback."""

    def test_load_existing_user(self, app):
        with app.app_context():
            user_data = app.user_manager.get_user('admin')
            assert user_data is not None

    def test_load_nonexistent_user(self, app):
        with app.app_context():
            user_data = app.user_manager.get_user('nonexistent_user_xyz')
            assert user_data is None


class TestContextProcessor:
    """Tests for context_processor in app.py."""

    def test_context_has_expected_values(self, app):
        with app.test_request_context():
            ctx = {}
            # Run all context processors
            for func in app.template_context_processors[None]:
                ctx.update(func())
            assert 'sap_available' in ctx
            assert 'UserRole' in ctx
            assert 'OrderStatus' in ctx


class TestFaviconAndIndex:
    """Tests for favicon and index redirect."""

    def test_index_redirect(self, auth_client):
        resp = auth_client.get('/', follow_redirects=False)
        assert resp.status_code == 302


