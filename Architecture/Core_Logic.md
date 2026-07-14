# 🧠 Core Logic

> `core/` — Business logic modules. Framework-agnostic managers that handle data, state, and integrations.

## Manager Overview

| Manager | File | Purpose | Depends On |
|---------|------|---------|------------|
| **OrderStatusManager** | [[Node_core_order_status_manager_py]] | Order lifecycle (status enum, transitions, persistence) | [[Node_core_database_client_py]] |
| **UserManager** | [[Node_core_user_manager_py]] | User CRUD, authentication, roles (UserRole enum) | [[Node_core_database_client_py]] |
| **SAPHanaConnector** | [[Node_core_sap_connector_py]] | Read-only queries to SAP HANA (orders, lines, invoices) | hdbcli, pandas |
| **DatabaseClient** | [[Node_core_database_client_py]] | SQL Server connection pool (pyodbc + sqlalchemy) | pyodbc, sqlalchemy |
| **RelacionManager** | [[Node_core_relacion_manager_py]] | Shipping relation documents management | [[Node_core_database_client_py]] |
| **FacturaMetadataManager** | [[Node_core_factura_metadata_manager_py]] | Invoice metadata, daily order/extra tracking | [[Node_core_database_client_py]] |
| **AuditManager** | [[Node_core_audit_manager_py]] | Audit trail logging for all state changes | [[Node_core_database_client_py]] |
| **PrintEventMatcher** | [[Node_core_print_event_matcher_py]] | Matches SGA print events to orders | — |
| **SAPSyncWorker** | [[Node_core_sap_sync_worker_py]] | Background thread that periodically syncs SAP data | [[Node_core_sap_connector_py]] |
| **SystemHealth** | [[Node_core_system_health_py]] | Health checks (SGA connectivity, uptime) | — |

## Dependency Graph

```
DatabaseClient ◀── OrderStatusManager
      ▲                    ▲
      │                    │
      ├── UserManager      ├── routes/orders.py
      ├── RelacionManager  ├── sync_orders_job.py
      ├── FacturaMetaMgr   └── sync_print_jobs_job.py
      ├── AuditManager
      └── sync_print_jobs_job.py

SAPHanaConnector ◀── SAPSyncWorker
      ▲                    ▲
      │                    │
      ├── app.py           └── app.py (background thread)
      └── routes/orders.py
```

## Data Files (in `core/`)
- `order_status_db.json` — Local JSON snapshot of all order statuses
- `factura_metadata.json` — Invoice metadata store
- `factura_daily_order.json` — Daily order tracking
- `factura_daily_extra.json` — Daily extra items

## Key Patterns
- All managers are **singletons** attached to `app` in [[App_Factory]]
- Managers use **`DatabaseClient`** for SQL Server access
- `OrderStatus` is an **Enum** with states: `PENDIENTE`, `EN_PROCESO`, `IMPRESO`, `EMPACADO`, `FACTURADO`, `ENTREGADO`, etc.
- `UserRole` is an **Enum**: `ADMIN`, `OPERATOR`, `VIEWER`, `SELLER`, `SELL_MANAGER`, `BILLING`

---
*Part of [[Home]] architecture*
