---
tags:
  - app-core
  - py
  - extensions
---
# 🔌 extensions.py

> Shared Flask extensions — created separately to avoid circular imports.

## Role
Instantiates the `Limiter` extension and provides a typed `current_app` proxy that routes can import without circular dependency on `app.py`.

## Exports
- `limiter` — Flask-Limiter instance (`500/min`, `20/sec`)
- `current_app` — Typed as `OpenOMSApp` for IDE autocompletion

## Depends On
- `flask_limiter` — Rate limiting
- [[Node_app_py]] — Type-checking import of `OpenOMSApp`

## Used By
- [[Node_app_py]] — `limiter.init_app(app)`
- [[Node_routes_auth_py]] — `limiter.limit("5 per minute")`
- [[Node_routes_orders_py]] — `current_app` access
- [[Node_routes_users_py]] — `current_app` access

## Part Of
- [[App_Factory]], [[Security]]
