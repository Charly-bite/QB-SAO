---
tags:
  - core
  - py
  - auth
---
# 👥 core/user_manager.py

> User management, authentication, and role system.

## Role
Handles user CRUD, password hashing (werkzeug), authentication, and defines the `UserRole` enum used across the entire application.

## Key Classes
- `UserRole(Enum)` — Roles: ADMIN, OPERATOR, VIEWER, SELLER, SELL_MANAGER, BILLING
- `UserManager` — Singleton for user operations

## Key Methods
- `authenticate(username, password)` — Verify credentials
- `get_user(id)` / `get_all_users()` — Query users
- `create_user()` / `update_user()` / `delete_user()` — CRUD
- `get_current_user()` — Get authenticated user data

## Depends On
- [[Node_core_database_client_py]] — SQL Server persistence
- `werkzeug.security` — Password hashing

## Used By
- [[Node_app_py]] — Instantiated as `app.user_manager`
- [[Node_models_py]] — `UserRole` enum import
- [[Node_routes_auth_py]] — Authentication
- [[Node_routes_users_py]] — User CRUD operations
- [[Node_routes_orders_py]] — Role-based filtering
- [[Node_scripts_reset_admin_py]] — Admin password reset

## Part Of
- [[Core_Logic]], [[Security]]
