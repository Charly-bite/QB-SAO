"""
User model tests — verifies role predicates, hierarchy, and property accessors.
"""
import pytest

from core.user_manager import UserRole
from models import User


def _make_user(**overrides):
    """Helper to build a User with sane defaults."""
    data = {
        'username': 'testuser',
        'full_name': 'Test User',
        'email': 'test@example.com',
        'role': 'viewer',
        'is_active': True,
        'must_change_password': False,
        'last_login': None,
        'warehouse': 'W1',
        'sap_seller_name': '',
    }
    data.update(overrides)
    return User(data)


class TestUserInit:
    """User.__init__ attribute mapping."""

    def test_username_mapped(self):
        u = _make_user(username='alice')
        assert u.username == 'alice'
        assert u.id == 'alice'

    def test_role_is_enum(self):
        u = _make_user(role='admin')
        assert u.role == UserRole.ADMIN

    def test_defaults_for_missing_keys(self):
        u = User({'username': 'minimal'})
        assert u.full_name == ''
        assert u.email == ''
        assert u.role == UserRole.VIEWER
        assert u.is_active is True
        assert u.sap_seller_name == ''

    def test_get_id_returns_string(self):
        u = _make_user(username='bob')
        assert u.get_id() == 'bob'
        assert isinstance(u.get_id(), str)


class TestIsActive:
    """is_active property reflects is_active_flag."""

    def test_active_user(self):
        u = _make_user(is_active=True)
        assert u.is_active is True

    def test_inactive_user(self):
        u = _make_user(is_active=False)
        assert u.is_active is False


class TestRolePredicates:
    """Role boolean helpers."""

    def test_admin_is_admin(self):
        u = _make_user(role='admin')
        assert u.is_admin() is True

    def test_viewer_is_not_admin(self):
        u = _make_user(role='viewer')
        assert u.is_admin() is False

    def test_admin_is_operator(self):
        u = _make_user(role='admin')
        assert u.is_operator() is True

    def test_operator_is_operator(self):
        u = _make_user(role='operator')
        assert u.is_operator() is True

    def test_viewer_is_not_operator(self):
        u = _make_user(role='viewer')
        assert u.is_operator() is False

    def test_seller_is_seller(self):
        u = _make_user(role='seller')
        assert u.is_seller() is True

    def test_admin_is_not_seller(self):
        u = _make_user(role='admin')
        assert u.is_seller() is False

    def test_sell_manager_is_sell_manager(self):
        u = _make_user(role='sell_manager')
        assert u.is_sell_manager() is True

    def test_viewer_is_not_sell_manager(self):
        u = _make_user(role='viewer')
        assert u.is_sell_manager() is False


class TestCanSeeAllOrders:
    """can_see_all_orders — admins, operators, sell_managers can see all."""

    @pytest.mark.parametrize('role', ['admin', 'operator', 'sell_manager'])
    def test_privileged_roles_can_see_all(self, role):
        u = _make_user(role=role)
        assert u.can_see_all_orders() is True

    @pytest.mark.parametrize('role', ['viewer', 'seller'])
    def test_restricted_roles_cannot_see_all(self, role):
        u = _make_user(role=role)
        assert u.can_see_all_orders() is False


class TestCanPrintLabels:
    """can_print_labels — operators + admins only."""

    @pytest.mark.parametrize('role', ['admin', 'operator'])
    def test_can_print(self, role):
        u = _make_user(role=role)
        assert u.can_print_labels() is True

    @pytest.mark.parametrize('role', ['viewer', 'seller', 'sell_manager'])
    def test_cannot_print(self, role):
        u = _make_user(role=role)
        assert u.can_print_labels() is False


class TestCanManageUsers:
    """can_manage_users — admin only."""

    def test_admin_can_manage(self):
        u = _make_user(role='admin')
        assert u.can_manage_users() is True

    @pytest.mark.parametrize('role', ['operator', 'viewer', 'seller', 'sell_manager'])
    def test_others_cannot_manage(self, role):
        u = _make_user(role=role)
        assert u.can_manage_users() is False


class TestHasRole:
    """has_role — hierarchical role check."""

    def test_admin_has_all_roles(self):
        u = _make_user(role='admin')
        assert u.has_role(UserRole.ADMIN) is True
        assert u.has_role(UserRole.OPERATOR) is True
        assert u.has_role(UserRole.VIEWER) is True

    def test_operator_has_operator_and_viewer(self):
        u = _make_user(role='operator')
        assert u.has_role(UserRole.OPERATOR) is True
        assert u.has_role(UserRole.VIEWER) is True
        assert u.has_role(UserRole.ADMIN) is False

    def test_viewer_has_only_viewer(self):
        u = _make_user(role='viewer')
        assert u.has_role(UserRole.VIEWER) is True
        assert u.has_role(UserRole.OPERATOR) is False
        assert u.has_role(UserRole.ADMIN) is False

    def test_seller_has_seller_level(self):
        u = _make_user(role='seller')
        assert u.has_role(UserRole.SELLER) is True
        assert u.has_role(UserRole.VIEWER) is True
        assert u.has_role(UserRole.OPERATOR) is False
