"""
User Manager — Open-OMS
Independent user management with SQL persistence.
Uses 'seguimiento_users' table.
"""

import datetime
import hashlib
import logging
import secrets
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class UserRole(Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"
    SELLER = "seller"
    SELL_MANAGER = "sell_manager"


class UserManager:
    """
    Manages users for Open-OMS.
    Uses 'seguimiento_users' SQL table (independent from SGA_dev).
    """

    TABLE_NAME = "seguimiento_users"

    def __init__(self, fallback_json_path: Optional[str] = None):
        self.users: Dict[str, Dict] = {}
        self.current_user = None
        self.sql_engine = None

        # Try SQL connection
        try:
            from core.database_client import DatabaseClient

            db = DatabaseClient()
            if db.connect():
                self.sql_engine = db.get_sql_engine()
        except Exception as e:
            logger.warning(f"UserManager SQL error: {e}")

        self._ensure_table_exists()
        self._load_users()

        # Create default admin if no users exist
        if not self.users:
            self._create_default_admin()

    def _ensure_table_exists(self):
        """Create seguimiento_users table if not exists."""
        if not self.sql_engine:
            return
        try:
            with self.sql_engine.begin() as conn:
                conn.exec_driver_sql(f"""
                    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{self.TABLE_NAME}' and xtype='U')
                    CREATE TABLE {self.TABLE_NAME} (
                        username VARCHAR(100) PRIMARY KEY,
                        password_hash VARCHAR(256),
                        salt VARCHAR(64),
                        full_name NVARCHAR(200),
                        email VARCHAR(200),
                        role VARCHAR(50) DEFAULT 'viewer',
                        is_active BIT DEFAULT 1,
                        must_change_password BIT DEFAULT 0,
                        last_login VARCHAR(50),
                        created_at VARCHAR(50),
                        warehouse VARCHAR(50) DEFAULT ''
                    )
                """)
        except Exception as e:
            logger.error(f"Could not create {self.TABLE_NAME}: {e}")

    def _load_users(self):
        """Load users from SQL table."""
        if not self.sql_engine:
            return

        try:
            with self.sql_engine.connect() as conn:
                result = conn.exec_driver_sql(f"SELECT * FROM {self.TABLE_NAME}")
                columns = result.keys()
                for row in result.fetchall():
                    user_data = dict(zip(columns, row))
                    username = user_data["username"]
                    self.users[username] = {
                        "username": username,
                        "password_hash": user_data.get("password_hash", ""),
                        "salt": user_data.get("salt", ""),
                        "full_name": user_data.get("full_name", ""),
                        "email": user_data.get("email", ""),
                        "role": user_data.get("role", "viewer"),
                        "is_active": bool(user_data.get("is_active", True)),
                        "must_change_password": bool(
                            user_data.get("must_change_password", False)
                        ),
                        "last_login": user_data.get("last_login"),
                        "created_at": user_data.get("created_at", ""),
                        "warehouse": user_data.get("warehouse", ""),
                        "sap_seller_name": user_data.get("sap_seller_name", ""),
                    }
            logger.info(f"✅ Loaded {len(self.users)} users from {self.TABLE_NAME}")
        except Exception as e:
            logger.warning(f"Could not load users from SQL: {e}")

    def _save_user_to_sql(self, user_data):
        """Save or update a single user in SQL."""
        if not self.sql_engine:
            return

        try:
            with self.sql_engine.connect() as conn:
                raw = conn.connection
                cursor = raw.cursor()

                # Upsert
                cursor.execute(
                    f"""
                    IF EXISTS (SELECT 1 FROM {self.TABLE_NAME} WHERE username = ?)
                        UPDATE {self.TABLE_NAME} SET
                            password_hash = ?, salt = ?, full_name = ?, email = ?,
                            role = ?, is_active = ?, must_change_password = ?,
                            last_login = ?, created_at = ?, warehouse = ?
                        WHERE username = ?
                    ELSE
                        INSERT INTO {self.TABLE_NAME}
                            (username, password_hash, salt, full_name, email, role,
                             is_active, must_change_password, last_login, created_at, warehouse)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        # For EXISTS check
                        user_data["username"],
                        # For UPDATE
                        user_data.get("password_hash", ""),
                        user_data.get("salt", ""),
                        user_data.get("full_name", ""),
                        user_data.get("email", ""),
                        user_data.get("role", "viewer"),
                        1 if user_data.get("is_active", True) else 0,
                        1 if user_data.get("must_change_password", False) else 0,
                        user_data.get("last_login"),
                        user_data.get("created_at", ""),
                        user_data.get("warehouse", ""),
                        user_data["username"],
                        # For INSERT
                        user_data["username"],
                        user_data.get("password_hash", ""),
                        user_data.get("salt", ""),
                        user_data.get("full_name", ""),
                        user_data.get("email", ""),
                        user_data.get("role", "viewer"),
                        1 if user_data.get("is_active", True) else 0,
                        1 if user_data.get("must_change_password", False) else 0,
                        user_data.get("last_login"),
                        user_data.get("created_at", ""),
                        user_data.get("warehouse", ""),
                    ],
                )
                raw.commit()
                cursor.close()
        except Exception as e:
            logger.error(f"Error saving user to SQL: {e}")

    def _create_default_admin(self):
        """Create default admin account."""
        salt = secrets.token_hex(16)
        password = "admin123"
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()

        admin_data = {
            "username": "admin",
            "password_hash": password_hash,
            "salt": salt,
            "full_name": "Administrador",
            "email": "",
            "role": "admin",
            "is_active": True,
            "must_change_password": False,
            "last_login": None,
            "created_at": datetime.datetime.now().isoformat(),
            "warehouse": "",
        }

        self.users["admin"] = admin_data
        self._save_user_to_sql(admin_data)
        print("✅ Default admin created (user: admin, pass: admin123)")

    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate a user."""
        user = self.users.get(username)
        if not user:
            return False

        if not user.get("is_active", True):
            return False

        salt = user.get("salt", "")
        expected_hash = user.get("password_hash", "")
        actual_hash = hashlib.sha256((password + salt).encode()).hexdigest()

        if actual_hash == expected_hash:
            # Update last login
            user["last_login"] = datetime.datetime.now().isoformat()
            self.current_user = user
            self._save_user_to_sql(user)
            return True

        return False

    def get_current_user(self) -> Optional[Dict]:
        """Get the currently authenticated user."""
        return self.current_user

    def get_user(self, username: str) -> Optional[Dict]:
        """Get user data by username."""
        return self.users.get(username)

    def get_all_users(self) -> List[Dict]:
        """Get all users."""
        return list(self.users.values())

    def create_user(
        self,
        username: str,
        password: str,
        full_name: str = "",
        email: str = "",
        role: str = "viewer",
        requesting_user=None,
        **kwargs,
    ) -> Tuple[bool, str]:
        """Create a new user."""
        if requesting_user:
            req_role = requesting_user.get("role", "viewer")
            if isinstance(req_role, UserRole):
                req_role = req_role.value
            if req_role != "admin":
                return False, "Solo administradores pueden crear usuarios"

        if username in self.users:
            return False, "El usuario ya existe"

        if len(password) < 6:
            return False, "La contraseña debe tener al menos 6 caracteres"

        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()

        user_data = {
            "username": username,
            "password_hash": password_hash,
            "salt": salt,
            "full_name": full_name,
            "email": email,
            "role": role,
            "is_active": True,
            "must_change_password": False,
            "last_login": None,
            "created_at": datetime.datetime.now().isoformat(),
            "warehouse": "",
            "sap_seller_name": kwargs.get("sap_seller_name", ""),
        }

        self.users[username] = user_data
        self._save_user_to_sql(user_data)
        return True, "Usuario creado exitosamente"

    def update_user(
        self, username: str, requesting_user=None, **kwargs
    ) -> Tuple[bool, str]:
        """Update user properties."""
        user = self.users.get(username)
        if not user:
            return False, "Usuario no encontrado"

        # Password change
        if "password" in kwargs:
            new_password = kwargs["password"]
            if len(new_password) < 6:
                return False, "La contraseña debe tener al menos 6 caracteres"
            salt = secrets.token_hex(16)
            user["salt"] = salt
            user["password_hash"] = hashlib.sha256(
                (new_password + salt).encode()
            ).hexdigest()
            user["must_change_password"] = False

        # Other fields
        for field in [
            "full_name",
            "email",
            "role",
            "is_active",
            "warehouse",
            "sap_seller_name",
        ]:
            if field in kwargs:
                user[field] = kwargs[field]

        self._save_user_to_sql(user)
        return True, "Usuario actualizado"

    def delete_user(self, username: str, requesting_user=None) -> Tuple[bool, str]:
        """Delete a user."""
        if username not in self.users:
            return False, "Usuario no encontrado"

        if username == "admin":
            return False, "No se puede eliminar al administrador"

        del self.users[username]

        if self.sql_engine:
            try:
                with self.sql_engine.connect() as conn:
                    raw = conn.connection
                    cursor = raw.cursor()
                    cursor.execute(
                        f"DELETE FROM {self.TABLE_NAME} WHERE username = ?", [username]
                    )
                    raw.commit()
                    cursor.close()
            except Exception as e:
                logger.error(f"Error deleting user from SQL: {e}")

        return True, "Usuario eliminado"

