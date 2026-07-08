"""
core/permission_manager.py
==========================
Manages role-based permissions for QB-SAO.

Permissions are stored in the `seguimiento_role_permissions` SQL table.
If the table is empty or a role has no row, safe built-in defaults are used.

Usage (on the Flask app object):
    app.permission_manager = PermissionManager()
    app.permission_manager.load(sql_engine)

Usage on a User object:
    user.has_permission('nav.pedidos')
"""

import json
import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

TABLE_NAME = "seguimiento_role_permissions"

# ── Permission catalogue ─────────────────────────────────────────────────────
#  Each key maps to a human-readable label shown in the admin checkbox UI.
PERMISSION_LABELS: Dict[str, str] = {
    # Navigation
    "nav.pedidos":           "Navegación — Pedidos",
    "nav.facturas":          "Navegación — Facturas",
    "nav.monitor":           "Navegación — Monitor",
    "nav.dashboard":         "Navegación — Dashboard",
    "nav.users":             "Navegación — Usuarios & Auditoría",
    # Facturas subtabs
    "facturas.tab.facturas":    "Facturas — Subtab Facturas",
    "facturas.tab.credito":     "Facturas — Subtab Crédito",
    "facturas.tab.relaciones":  "Facturas — Subtab Relaciones",
    "facturas.tab.pendientes":  "Facturas — Subtab Pendientes",
    "facturas.tab.almacen":     "Facturas — Subtab Almacén",
    # Facturas actions
    "facturas.edit":             "Facturas — Añadir / editar facturas",
    "facturas.sign.facturacion": "Facturas — Firmar columna Facturación",
    "facturas.sign.credito":     "Facturas — Firmar columna Crédito",
    "facturas.sign.almacen":     "Facturas — Firmar columna Almacén",
    "facturas.authorize":        "Facturas — Autorizar / revocar crédito",
    # Orders
    "orders.edit":          "Pedidos — Editar / cambiar estado",
    "orders.print_labels":  "Pedidos — Imprimir etiquetas",
    "orders.see_all":       "Pedidos — Ver todos los pedidos",
}

# ── Default permissions per role ─────────────────────────────────────────────
_ALL = set(PERMISSION_LABELS.keys())

DEFAULT_PERMISSIONS: Dict[str, Set[str]] = {
    "admin": _ALL.copy(),

    "operator": {
        "nav.pedidos", "nav.facturas", "nav.monitor",
        "facturas.tab.facturas", "facturas.tab.relaciones", "facturas.tab.almacen",
        "facturas.sign.almacen",
        "orders.edit", "orders.print_labels", "orders.see_all",
    },

    "facturacion": {
        "nav.pedidos", "nav.facturas",
        "facturas.tab.facturas", "facturas.tab.relaciones", "facturas.tab.pendientes",
        "facturas.edit", "facturas.sign.facturacion",
        "orders.see_all",
    },

    "credito": {
        "nav.facturas",
        "facturas.tab.credito", "facturas.tab.relaciones",
        "facturas.sign.credito", "facturas.authorize",
        "orders.see_all",
    },

    "sell_manager": {
        "nav.pedidos", "nav.facturas", "nav.monitor",
        "facturas.tab.facturas", "facturas.tab.credito", "facturas.tab.relaciones",
        "orders.edit", "orders.see_all",
    },

    "seller": {
        "nav.pedidos",
    },

    "viewer": {
        "nav.pedidos", "nav.monitor", "nav.dashboard",
        "orders.see_all",
    },

    # Legacy — same as facturacion during transition
    "billing": {
        "nav.pedidos", "nav.facturas",
        "facturas.tab.facturas", "facturas.tab.relaciones", "facturas.tab.pendientes",
        "facturas.edit", "facturas.sign.facturacion",
        "orders.see_all",
    },
}


class PermissionManager:
    """
    Loads, caches, and persists role permissions.

    The effective permission set for a role =
        DB row (if present) else DEFAULT_PERMISSIONS[role]
    """

    def __init__(self):
        # role → frozenset of permission strings
        self._cache: Dict[str, frozenset] = {}
        self._sql_engine = None
        # Seed with defaults so the manager is usable even without a DB
        self._reset_to_defaults()

    # ── Public API ───────────────────────────────────────────────────────────

    def load(self, sql_engine) -> None:
        """
        Load permission overrides from the DB.
        Falls back to built-in defaults if the table is empty or unreachable.
        """
        self._sql_engine = sql_engine
        if not sql_engine:
            logger.warning("[PermissionManager] No SQL engine — using defaults.")
            return

        try:
            self._ensure_table(sql_engine)
            self._load_from_db(sql_engine)
        except Exception as e:
            logger.error(f"[PermissionManager] Failed to load from DB: {e}. Using defaults.")

    def has_permission(self, role: str, key: str) -> bool:
        """Fast membership test for a single permission key."""
        return key in self._cache.get(role, frozenset())

    def get_permissions(self, role: str) -> Set[str]:
        """Return the full set of permissions for a role (mutable copy)."""
        return set(self._cache.get(role, DEFAULT_PERMISSIONS.get(role, set())))

    def get_all(self) -> Dict[str, Set[str]]:
        """Return a dict of {role: set_of_permissions} for every known role."""
        return {role: set(perms) for role, perms in self._cache.items()}

    def set_permissions(self, role: str, permissions: list) -> bool:
        """
        Persist a new permission set for a role.
        Returns True on success, False on DB error.
        """
        perm_set = frozenset(k for k in permissions if k in PERMISSION_LABELS)

        if self._sql_engine:
            try:
                with self._sql_engine.begin() as conn:
                    conn.exec_driver_sql(
                        f"DELETE FROM {TABLE_NAME} WHERE role = ?", (role,)
                    )
                    if perm_set:
                        conn.exec_driver_sql(
                            f"INSERT INTO {TABLE_NAME} (role, permissions_json) VALUES (?, ?)",
                            (role, json.dumps(sorted(perm_set)))
                        )
                logger.info(f"[PermissionManager] Saved permissions for role '{role}'.")
            except Exception as e:
                logger.error(f"[PermissionManager] Failed to save permissions: {e}")
                return False

        # Update in-memory cache immediately (no restart needed)
        self._cache[role] = perm_set
        return True

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _reset_to_defaults(self):
        self._cache = {
            role: frozenset(perms)
            for role, perms in DEFAULT_PERMISSIONS.items()
        }

    def _ensure_table(self, engine) -> None:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"""
                IF NOT EXISTS (
                    SELECT * FROM sysobjects
                    WHERE name='{TABLE_NAME}' AND xtype='U'
                )
                CREATE TABLE {TABLE_NAME} (
                    role             VARCHAR(50)   NOT NULL PRIMARY KEY,
                    permissions_json NVARCHAR(MAX) NOT NULL
                )
            """)

    def _load_from_db(self, engine) -> None:
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                f"SELECT role, permissions_json FROM {TABLE_NAME}"
            ).fetchall()

        loaded = 0
        for role, perm_json in rows:
            try:
                perms = json.loads(perm_json)
                self._cache[role] = frozenset(
                    k for k in perms if k in PERMISSION_LABELS
                )
                loaded += 1
            except Exception as e:
                logger.warning(f"[PermissionManager] Bad JSON for role '{role}': {e}")

        if loaded:
            logger.info(f"[PermissionManager] Loaded DB overrides for {loaded} roles.")
        else:
            logger.info("[PermissionManager] No DB overrides found — using defaults.")
