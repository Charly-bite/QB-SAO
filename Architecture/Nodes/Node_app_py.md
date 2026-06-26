---
tags:
  - app-core
  - py
  - entry-point
---
# 📦 app.py

> **Main entry point** for Open-OMS. Implements the Flask application factory pattern.

## Role
Creates and configures the Flask application, initializes all extensions, attaches business logic managers, registers route blueprints, and starts background workers.

## Key Functions
- `create_app(config_name)` — Application factory
- `OpenOMSApp` — Custom Flask subclass with typed attributes

## Depends On
- [[Node_config_py]] — Multi-environment configuration
- [[Node_extensions_py]] — Rate limiter, typed `current_app`
- [[Node_models_py]] — `User` class for Flask-Login
- [[Node_core_order_status_manager_py]] — Order lifecycle management
- [[Node_core_user_manager_py]] — User CRUD + auth
- [[Node_core_sap_connector_py]] — SAP HANA connection (optional)
- [[Node_core_factura_metadata_manager_py]] — Invoice metadata
- [[Node_core_relacion_manager_py]] — Shipping relations
- [[Node_core_audit_manager_py]] — Audit trail
- [[Node_core_sap_sync_worker_py]] — Background sync thread
- [[Node_core_system_health_py]] — SGA health checks
- [[Node_routes_auth_py]] — Auth blueprint
- [[Node_routes_orders_py]] — Orders blueprint
- [[Node_routes_users_py]] — Users blueprint
- [[Node_middleware_request_logger_py]] — Request logging

## Used By
- [[Node_scripts_sync_orders_job_py]] — `create_app()` for app context
- [[Node_scripts_sync_print_jobs_job_py]] — `create_app()` for app context
- [[Node_scripts_reset_admin_py]] — `create_app()` for admin reset
- [[Node_test_mostrador_py]] — Test client
- [[Node_test_shipping_py]] — Test client
- [[Node_extensions_py]] — Type-checking import of `OpenOMSApp`

## Part Of
- [[App_Factory]]
