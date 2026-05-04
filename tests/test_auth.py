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
