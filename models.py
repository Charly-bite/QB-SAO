"""
User model for Flask-Login integration
"""
from flask_login import UserMixin
from core.user_manager import UserRole


class User(UserMixin):
    """User model compatible with Flask-Login"""

    def __init__(self, user_data: dict):
        self.id = user_data.get('username')
        self.username = user_data.get('username')
        self.full_name = user_data.get('full_name', '')
        self.email = user_data.get('email', '')
        self.role = UserRole(user_data.get('role', 'viewer'))
        self.is_active_flag = user_data.get('is_active', True)
        self.must_change_password = user_data.get('must_change_password', False)
        self.last_login = user_data.get('last_login')
        self.warehouse = user_data.get('warehouse', '')

    def get_id(self):
        return self.username

    @property
    def is_active(self):
        return self.is_active_flag

    def is_admin(self):
        return self.role == UserRole.ADMIN

    def is_operator(self):
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR]

    def has_role(self, role: UserRole):
        role_hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.OPERATOR: 1,
            UserRole.ADMIN: 2
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(role, 0)

    def can_print_labels(self):
        """Operators and Admins can manage orders."""
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR]

    def can_manage_users(self):
        return self.role == UserRole.ADMIN
