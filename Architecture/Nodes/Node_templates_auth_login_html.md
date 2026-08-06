---
tags:
  - template
  - html
  - auth
---
# 🔐 templates/auth/login.html

> **Login page** — user authentication with styled login form.

## Extends
- [[Node_templates_base_html]]

## Served By
- [[Node_routes_auth_py]] — `GET /login`

## Features
- Username/password form with CSRF token
- "Remember me" checkbox
- Rate limited to 5 POST/min via [[Node_extensions_py]]
- Auto-redirect for already-authenticated users

## Part Of
- [[Frontend]], [[Security]]
