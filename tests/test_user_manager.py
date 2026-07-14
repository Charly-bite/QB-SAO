"""
Unit tests for UserManager — pure business logic.
These tests run without SQL Server.
"""
import pytest
from unittest.mock import patch, MagicMock


def _make_mock_db_client():
    """Return a mock DatabaseClient class that never connects."""
    mock_cls = MagicMock()
    inst = MagicMock()
    inst.connect.return_value = False
    inst.get_sql_engine.return_value = None
    mock_cls.return_value = inst
    return mock_cls


@pytest.fixture()
def um():
    """Create a UserManager with no SQL backend."""
    mock_cls = _make_mock_db_client()
    with patch('core.database_client.DatabaseClient', mock_cls):
        from core.user_manager import UserManager
        mgr = UserManager()
    return mgr


class TestDefaultAdmin:

    def test_default_admin_exists(self, um):
        assert 'admin' in um.users

    def test_default_admin_is_admin_role(self, um):
        assert um.users['admin']['role'] == 'admin'

    def test_default_admin_authenticates(self, um):
        assert um.authenticate('admin', 'admin123') is True

    def test_default_admin_wrong_password(self, um):
        assert um.authenticate('admin', 'wrong') is False


class TestUserCreation:

    def test_create_user_success(self, um):
        success, msg = um.create_user('newuser', 'pass123456', full_name='New User')
        assert success is True
        assert 'newuser' in um.users

    def test_create_duplicate_fails(self, um):
        um.create_user('dup', 'pass123456')
        success, msg = um.create_user('dup', 'pass123456')
        assert success is False
        assert 'existe' in msg.lower()

    def test_create_short_password_fails(self, um):
        success, msg = um.create_user('shortpw', '123')
        assert success is False

    def test_create_user_default_role(self, um):
        um.create_user('defaultrole', 'pass123456')
        assert um.users['defaultrole']['role'] == 'viewer'

    def test_create_user_with_role(self, um):
        um.create_user('opr', 'pass123456', role='operator')
        assert um.users['opr']['role'] == 'operator'

    def test_non_admin_cannot_create(self, um):
        requesting = {'username': 'viewer1', 'role': 'viewer'}
        success, msg = um.create_user('x', 'pass123456', requesting_user=requesting)
        assert success is False


class TestAuthentication:

    def test_authenticate_valid(self, um):
        um.create_user('authtest', 'mypassword')
        assert um.authenticate('authtest', 'mypassword') is True

    def test_authenticate_invalid_password(self, um):
        um.create_user('authtest2', 'correct')
        assert um.authenticate('authtest2', 'incorrect') is False

    def test_authenticate_nonexistent_user(self, um):
        assert um.authenticate('ghost', 'anything') is False

    def test_authenticate_inactive_user(self, um):
        um.create_user('inactive', 'pass123456')
        um.users['inactive']['is_active'] = False
        assert um.authenticate('inactive', 'pass123456') is False

    def test_last_login_updated(self, um):
        um.create_user('logintrack', 'pass123456')
        assert um.users['logintrack']['last_login'] is None
        um.authenticate('logintrack', 'pass123456')
        assert um.users['logintrack']['last_login'] is not None


class TestUserUpdate:

    def test_update_full_name(self, um):
        um.create_user('upd', 'pass123456', full_name='Old Name')
        success, _ = um.update_user('upd', full_name='New Name')
        assert success is True
        assert um.users['upd']['full_name'] == 'New Name'

    def test_update_password(self, um):
        um.create_user('pwupd', 'oldpass123')
        um.update_user('pwupd', password='newpass123')
        assert um.authenticate('pwupd', 'newpass123') is True
        assert um.authenticate('pwupd', 'oldpass123') is False

    def test_update_short_password_fails(self, um):
        um.create_user('shortupd', 'pass123456')
        success, _ = um.update_user('shortupd', password='ab')
        assert success is False

    def test_update_nonexistent_user(self, um):
        success, _ = um.update_user('ghost', full_name='X')
        assert success is False

    def test_update_role(self, um):
        um.create_user('roleupd', 'pass123456', role='viewer')
        um.update_user('roleupd', role='operator')
        assert um.users['roleupd']['role'] == 'operator'


class TestUserDeletion:

    def test_delete_user(self, um):
        um.create_user('delme', 'pass123456')
        success, _ = um.delete_user('delme')
        assert success is True
        assert 'delme' not in um.users

    def test_delete_admin_blocked(self, um):
        success, msg = um.delete_user('admin')
        assert success is False

    def test_delete_nonexistent(self, um):
        success, _ = um.delete_user('ghost')
        assert success is False


class TestUserRetrieval:

    def test_get_user(self, um):
        um.create_user('getme', 'pass123456', full_name='Get Me')
        user = um.get_user('getme')
        assert user is not None
        assert user['full_name'] == 'Get Me'

    def test_get_nonexistent_returns_none(self, um):
        assert um.get_user('nope') is None

    def test_get_all_users(self, um):
        users = um.get_all_users()
        assert len(users) >= 1  # at least the default admin
