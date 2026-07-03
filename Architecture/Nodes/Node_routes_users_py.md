---
tags:
  - routes
  - py
  - users
---
# 👤 routes/users.py

> User management blueprint — CRUD operations for user accounts.

## Role
Admin-only interface for creating, editing, and listing user accounts. Requires `can_view_users()` permission.

## Endpoints
| Route | Method | Template |
|-------|--------|----------|
| `/users/` | GET | [[Node_templates_users_list_html]] |
| `/users/create` | GET/POST | [[Node_templates_users_form_html]] |
| `/users/<id>/edit` | GET/POST | [[Node_templates_users_form_html]] |

## Depends On
- [[Node_extensions_py]] — `current_app`
- [[Node_core_user_manager_py]] — `UserRole`, user CRUD

## Used By
- [[Node_app_py]] — Registered as `users_bp` blueprint

## Part Of
- [[Routes]]
