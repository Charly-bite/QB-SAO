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
        self.signature_path = user_data.get("signature_path", "")

        # Permission set — injected by app.py user_loader via PermissionManager.
        # Falls back to empty set; has_permission() returns False gracefully.
        self._permissions: frozenset = frozenset()

    def get_id(self) -> str:
        return str(self.username) if self.username else ""

    @property
    def is_active(self):
        return self.is_active_flag

    # ── Core permission check ─────────────────────────────────────────────────

    def has_permission(self, key: str) -> bool:
        """
        Dynamic permission check against the PermissionManager's ruleset.
        Admins always have every permission regardless of DB configuration.
        """
        if self.role == UserRole.ADMIN:
            return True
        # Explicitly block dashboard permission for ReyesM
        if self.username and self.username.lower() == "reyesm" and key == "nav.dashboard":
            return False
        # Special check for user ReyesM (jefe de almacén)
        if self.username and self.username.lower() == "reyesm":
            if key in (
                "nav.facturas",
                "nav.monitor",
                "facturas.tab.relaciones",
                "facturas.tab.pendientes",
                "facturas.tab.almacen",
            ):
                return True
        if not self._permissions:
            from flask import current_app
            if current_app:
                pm = getattr(current_app, "permission_manager", None)
                if pm:
                    return pm.has_permission(self.role.value, key)
        return key in self._permissions

    # ── Convenience helpers (delegate to has_permission) ─────────────────────
    # Kept for backward compatibility with existing templates and routes.

    def is_admin(self):
        return self.role == UserRole.ADMIN

    def is_operator(self):
        return self.role in (UserRole.ADMIN, UserRole.OPERATOR)

    def is_seller(self):
        """Seller role — can only see own orders in monitor."""
        return self.role == UserRole.SELLER

    def is_sell_manager(self):
        """Selling manager — can see all seller orders with filter."""
        return self.role == UserRole.SELL_MANAGER

    def is_billing(self):  # pragma: no cover
        """Legacy check — maps to facturacion role."""
        return self.role in (UserRole.BILLING, UserRole.FACTURACION)

    def is_facturacion(self):  # pragma: no cover
        return self.role == UserRole.FACTURACION

    def is_credito(self):  # pragma: no cover
        return self.role == UserRole.CREDITO

    def can_edit_facturas(self):  # pragma: no cover
        return self.has_permission("facturas.edit")

    def can_see_all_orders(self):
        return self.has_permission("orders.see_all")

    def can_view_dashboard(self):
        return self.has_permission("nav.dashboard")

    def can_view_users(self):
        return self.has_permission("nav.users")

    def can_edit_orders(self):
        return self.has_permission("orders.edit")

    def has_role(self, role: UserRole):
        role_hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.SELLER: 0,
            UserRole.BILLING: 0,
            UserRole.CREDITO: 0,
            UserRole.FACTURACION: 0,
            UserRole.SELL_MANAGER: 1,
            UserRole.OPERATOR: 1,
            UserRole.ADMIN: 2,
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(role, 0)

    def can_print_labels(self):
        """Operators and Admins can print labels."""
        return self.has_permission("orders.print_labels")

    def can_manage_users(self):
        return self.role == UserRole.ADMIN

    # ── Signature / signing permissions ──────────────────────────────────────

    def can_sign_facturacion(self):  # pragma: no cover
        return self.has_permission("facturas.sign.facturacion")

    def can_sign_credito(self):  # pragma: no cover
        return self.has_permission("facturas.sign.credito")

    def can_sign_almacen(self):  # pragma: no cover
        return self.has_permission("facturas.sign.almacen")

    def can_authorize_credito(self):  # pragma: no cover
        return self.has_permission("facturas.authorize")
