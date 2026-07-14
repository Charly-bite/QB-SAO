---
tags:
  - app-core
  - py
  - auth
---
# 👤 models.py

> User model for Flask-Login integration.

## Role
Defines the `User` class that wraps user data dictionaries from [[Node_core_user_manager_py]] into a Flask-Login compatible object with role-based permission methods.

## Key Class: `User(UserMixin)`
### Permission Methods
| Method | Allowed Roles |
|--------|--------------|
| `is_admin()` | ADMIN |
| `is_operator()` | ADMIN, OPERATOR |
| `is_seller()` | SELLER |
| `is_sell_manager()` | SELL_MANAGER |
| `is_billing()` | BILLING |
| `can_edit_facturas()` | ADMIN, OPERATOR, SELL_MANAGER, BILLING |
| `can_see_all_orders()` | ADMIN, OPERATOR, SELL_MANAGER, BILLING, VIEWER |
| `can_print_labels()` | ADMIN, OPERATOR |
| `can_manage_users()` | ADMIN |
| `can_sign_facturacion()` | ADMIN, BILLING |
| `can_sign_credito()` | ADMIN, BILLING |
| `can_sign_almacen()` | ADMIN, OPERATOR |

## Depends On
- [[Node_core_user_manager_py]] — `UserRole` enum
- `flask_login` — `UserMixin` base class

## Used By
- [[Node_app_py]] — User loader callback
- [[Node_routes_auth_py]] — Login user creation
- All templates via `current_user` (Jinja2 context)

## Part Of
- [[Security]], [[App_Factory]]
