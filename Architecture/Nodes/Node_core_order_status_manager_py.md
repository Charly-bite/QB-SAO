---
tags:
  - core
  - py
  - business-logic
---
# 📋 core/order_status_manager.py

> **Central state machine** for order lifecycle management. The heart of Open-OMS.

## Role
Manages the complete lifecycle of orders: creation, status transitions, persistence to SQL Server, and in-memory caching. Defines the `OrderStatus` enum used throughout the app.

## Key Classes
- `OrderStatus(Enum)` — Status states: PENDIENTE, EN_PROCESO, IMPRESO, EMPACADO, FACTURADO, ENTREGADO, etc.
- `OrderStatusManager` — Singleton managing all order data

## Key Methods
- `get_order(order_id)` / `get_active_orders()` — Query orders
- `update_status(order_id, new_status)` — Transition order state
- `import_from_sap(sap_data)` — Import SAP orders into tracking
- `save()` / `load()` — Persist to/from `order_status_db.json` and SQL Server

## Depends On
- [[Node_core_database_client_py]] — SQL Server read/write
- Standard library: json, datetime, logging, enum

## Used By
- [[Node_app_py]] — Instantiated as `app.order_status_mgr`
- [[Node_routes_orders_py]] — All order operations
- [[Node_core_sap_sync_worker_py]] — Background sync updates
- [[Node_scripts_sync_orders_job_py]] — Scheduled sync
- [[Node_scripts_sync_print_jobs_job_py]] — Print event updates
- [[Node_scripts_audit_sga_sao_py]] — Audit comparison
- [[Node_test_mostrador_py]] — Testing
- [[Node_test_shipping_py]] — Testing

## Part Of
- [[Core_Logic]], [[Database]]
