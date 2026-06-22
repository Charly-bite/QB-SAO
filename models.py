"""
User model for Flask-Login integration
"""

from flask_login import UserMixin

from core.user_manager import UserRole


class User(UserMixin):
    """User model compatible with Flask-Login"""

    def __init__(self, user_data: dict):
        self.id = user_data.get("username")
        self.username = user_data.get("username")
        self.full_name = user_data.get("full_name", "")
        self.email = user_data.get("email", "")
        self.role = UserRole(user_data.get("role", "viewer"))
        self.is_active_flag = user_data.get("is_active", True)
        self.must_change_password = user_data.get("must_change_password", False)
        self.last_login = user_data.get("last_login")
        self.warehouse = user_data.get("warehouse", "")
        self.sap_seller_name = user_data.get("sap_seller_name", "")

    def get_id(self) -> str:
        return str(self.username) if self.username else ""

    @property
    def is_active(self):
        return self.is_active_flag

    def is_admin(self):
        return self.role == UserRole.ADMIN

    def is_operator(self):
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR]

    def is_seller(self):
        """Seller role — can only see own orders in monitor."""
        return self.role == UserRole.SELLER

    def is_sell_manager(self):
        """Selling manager — can see all seller orders with filter."""
        return self.role == UserRole.SELL_MANAGER

    def is_billing(self):
        """Billing role — can see billing info and all orders."""
        return self.role == UserRole.BILLING

    def can_edit_facturas(self):
        """Admins, operators, sell_managers, and billing can edit facturas."""
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR, UserRole.SELL_MANAGER, UserRole.BILLING]

    def can_see_all_orders(self):
        """Admins, operators, sell_managers, billing, and viewers can see all orders."""
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR, UserRole.SELL_MANAGER, UserRole.BILLING, UserRole.VIEWER]

    def can_view_dashboard(self):
        return self.role in [UserRole.ADMIN, UserRole.VIEWER]

    def can_view_users(self):
        return self.role in [UserRole.ADMIN, UserRole.VIEWER]

    def can_edit_orders(self):
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR, UserRole.SELL_MANAGER, UserRole.BILLING]

    def has_role(self, role: UserRole):
        role_hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.SELLER: 0,
            UserRole.BILLING: 0,
            UserRole.SELL_MANAGER: 1,
            UserRole.OPERATOR: 1,
            UserRole.ADMIN: 2,
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(role, 0)

    def can_print_labels(self):
        """Operators and Admins can manage orders."""
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR]

    def can_manage_users(self):
        return self.role == UserRole.ADMIN

    # ── Signature Permissions ────────────────────────────────────────────
    # These control who can sign each area of the Relación de Envíos.
    # Configure roles here once department bosses are assigned.

    def can_sign_facturacion(self):
        """Facturación department boss — billing role or admin."""
        return self.role in [UserRole.ADMIN, UserRole.BILLING]

    def can_sign_credito(self):
        """Crédito y Cobranza (Payments) department boss — billing role or admin."""
        return self.role in [UserRole.ADMIN, UserRole.BILLING]

    def can_sign_almacen(self):
        """Almacén (Warehouse) department boss — operator role or admin."""
        return self.role in [UserRole.ADMIN, UserRole.OPERATOR]
