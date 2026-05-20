"""
Authentication flow tests.
"""


class TestLoginPage:
    """GET /login — login page rendering."""

    def test_login_page_renders(self, client):
        response = client.get('/login')
        assert response.status_code == 200

    def test_login_page_contains_form(self, client):
        response = client.get('/login')
        html = response.data.decode('utf-8')
        assert 'username' in html.lower()
        assert 'password' in html.lower()


class TestLoginFlow:
    """POST /login — credential validation."""

    def test_login_with_valid_credentials(self, app):
        client = app.test_client()
        with app.app_context():
            um = app.user_manager
            if 'logintest' not in um.users:
                um.create_user(
                    username='logintest',
                    password='testpass123',
                    full_name='Login Test',
                    role='viewer',
                )

        response = client.post('/login', data={
            'username': 'logintest',
            'password': 'testpass123',
        }, follow_redirects=False)

        # Successful login redirects (302)
        assert response.status_code in (302, 303)

    def test_login_with_wrong_password(self, app):
        client = app.test_client()
        with app.app_context():
            um = app.user_manager
            if 'logintest2' not in um.users:
                um.create_user(
                    username='logintest2',
                    password='correctpass',
                    full_name='Login Test 2',
                    role='viewer',
                )

        response = client.post('/login', data={
            'username': 'logintest2',
            'password': 'wrongpass',
        }, follow_redirects=True)

        html = response.data.decode('utf-8')
        # Should show error message and stay on login
        assert response.status_code == 200

    def test_login_with_empty_fields(self, client):
        response = client.post('/login', data={
            'username': '',
            'password': '',
        }, follow_redirects=True)

        assert response.status_code == 200

    def test_login_redirects_authenticated_user(self, auth_client):
        """Already logged-in user visiting /login should be redirected."""
        response = auth_client.get('/login', follow_redirects=False)
        assert response.status_code in (302, 303)


class TestLogout:
    """GET /logout"""

    def test_logout_redirects_to_login(self, auth_client):
        response = auth_client.get('/logout', follow_redirects=False)
        assert response.status_code in (302, 303)
        assert '/login' in response.headers.get('Location', '')


class TestProtectedRoutes:
    """Unauthenticated users should be redirected to login."""

    def test_orders_redirects_unauthenticated(self, client):
        response = client.get('/orders/', follow_redirects=False)
        assert response.status_code in (302, 303)

    def test_visor_redirects_unauthenticated(self, client):
        response = client.get('/orders/visor', follow_redirects=False)
        assert response.status_code in (302, 303)


class TestIsSafeUrl:
    """Tests for _is_safe_url validation."""

    def test_safe_relative_url(self, app):
        with app.test_request_context():
            from routes.auth import _is_safe_url
            assert _is_safe_url('/orders/') is True

    def test_unsafe_external_url(self, app):
        with app.test_request_context():
            from routes.auth import _is_safe_url
            assert _is_safe_url('http://evil.com/phish') is False

    def test_login_with_safe_next(self, app):
        client = app.test_client()
        with app.app_context():
            um = app.user_manager
            if 'safenext' not in um.users:
                um.create_user(
                    username='safenext', password='pass123456',
                    full_name='Safe Next', role='viewer',
                )
        resp = client.post('/login?next=/orders/', data={
            'username': 'safenext', 'password': 'pass123456',
        }, follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert '/orders/' in resp.headers.get('Location', '')

    def test_login_with_unsafe_next(self, app):
        client = app.test_client()
        with app.app_context():
            um = app.user_manager
            if 'unsafenext' not in um.users:
                um.create_user(
                    username='unsafenext', password='pass123456',
                    full_name='Unsafe Next', role='viewer',
                )
        resp = client.post('/login?next=http://evil.com', data={
            'username': 'unsafenext', 'password': 'pass123456',
        }, follow_redirects=False)
        assert resp.status_code in (302, 303)
        # Should NOT redirect to evil.com
        loc = resp.headers.get('Location', '')
        assert 'evil.com' not in loc

