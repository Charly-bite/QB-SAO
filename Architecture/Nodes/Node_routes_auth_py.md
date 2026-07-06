---
tags:
  - routes
  - py
  - auth
---
# 🔐 routes/auth.py

> Authentication blueprint — login, logout, password change.

## Role
Handles user authentication flows: login form, credential verification, session management, forced password changes, and logout.

## Endpoints
| Route | Method | Description |
|-------|--------|-------------|
| `/login` | GET/POST | Login page + auth |
| `/logout` | GET | Session destroy |
| `/change-password` | GET/POST | Forced password change |

## Templates Served
- [[Node_templates_auth_login_html]]
- [[Node_templates_auth_change_password_html]]

## Depends On
- [[Node_extensions_py]] — `current_app`, `limiter`
- [[Node_models_py]] — `User` class
- [[Node_core_user_manager_py]] — Authentication (via `current_app.user_manager`)

## Used By
- [[Node_app_py]] — Registered as `auth_bp` blueprint

## Part Of
- [[Routes]], [[Security]]
