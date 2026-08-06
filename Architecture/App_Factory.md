# 🏭 App Factory

> `app.py` — The main entry point for Open-OMS. Uses Flask's **application factory pattern**.

## What It Does

1. **Creates the Flask app** via `create_app()` using [[Node_config_py]] for multi-environment settings
2. **Initializes security**: CSRF protection, rate limiting via [[Node_extensions_py]]
3. **Boots Flask-Login** with user loader that uses [[Node_models_py]] and [[Node_core_user_manager_py]]
4. **Instantiates all managers** from [[Core_Logic]]:
   - `OrderStatusManager` → [[Node_core_order_status_manager_py]]
   - `UserManager` → [[Node_core_user_manager_py]]
   - `FacturaMetadataManager` → [[Node_core_factura_metadata_manager_py]]
   - `RelacionManager` → [[Node_core_relacion_manager_py]]
   - `AuditManager` → [[Node_core_audit_manager_py]]
5. **Connects to SAP** (lazy) via [[Node_core_sap_connector_py]]
6. **Registers blueprints** from [[Routes]]:
   - `auth_bp` → [[Node_routes_auth_py]]
   - `orders_bp` → [[Node_routes_orders_py]]
   - `users_bp` → [[Node_routes_users_py]]
7. **Attaches middleware**: [[Node_middleware_request_logger_py]]
8. **Starts background worker**: [[Node_core_sap_sync_worker_py]]
9. **Context processor** injects `sap_available`, `sga_available`, `UserRole`, `OrderStatus` into all templates

## Dependency Graph

```
config.py ──▶ create_app()
extensions.py ──▶ limiter, current_app
                      │
          ┌───────────┼───────────────┐
          ▼           ▼               ▼
     UserManager  OrderStatusMgr  SAPConnector
          │           │               │
          ▼           ▼               ▼
    routes/auth   routes/orders   routes/users
          │           │               │
          ▼           ▼               ▼
       templates   templates      templates
```

## Key File
- **Source**: [[Node_app_py]]
- **Config**: [[Node_config_py]]
- **Extensions**: [[Node_extensions_py]]

---
*Part of [[Home]] architecture*
