---
tags:
  - scripts
  - py
  - admin
---
# 🔑 scripts/reset_admin.py

> **Admin password reset** — emergency admin credential reset.

## Role
Creates a Flask app context and resets the admin user's password using `UserManager`.

## Depends On
- [[Node_app_py]] — `create_app()` for Flask context
- [[Node_core_user_manager_py]] — Password reset (via `app.user_manager`)

## Part Of
- [[Scripts]]
