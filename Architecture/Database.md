# 🗄️ Database Connections

> The application relies on **two data sources** for its dual-database architecture.

## 1. Local SQL Server

| Aspect | Detail |
|--------|--------|
| **Client** | [[Node_core_database_client_py]] |
| **Driver** | `pyodbc` + `sqlalchemy` |
| **Purpose** | Stores users, order tracking status, audit logs, relaciones, factura metadata |
| **Access Pattern** | Read/Write via all managers in [[Core_Logic]] |

### Who Uses SQL Server?
- [[Node_core_order_status_manager_py]] — Order status CRUD
- [[Node_core_user_manager_py]] — User accounts & auth
- [[Node_core_relacion_manager_py]] — Shipping relations
- [[Node_core_factura_metadata_manager_py]] — Invoice metadata
- [[Node_core_audit_manager_py]] — Audit trail
- [[Node_scripts_sync_print_jobs_job_py]] — Print job sync

## 2. SAP HANA (ERP)

| Aspect | Detail |
|--------|--------|
| **Client** | [[Node_core_sap_connector_py]] |
| **Driver** | `hdbcli` (SAP HANA client) |
| **Purpose** | Read-only access to SAP Business One (orders, lines, invoices, customers) |
| **Access Pattern** | Read-only, synced periodically by [[Background_Jobs]] |

### Who Uses SAP HANA?
- [[Node_core_sap_connector_py]] — Direct queries
- [[Node_core_sap_sync_worker_py]] — Background sync thread
- [[Node_routes_orders_py]] — On-demand SAP data refresh
- [[Node_scripts_sync_orders_job_py]] — Scheduled sync job
- [[Node_scripts_backfill_auto_status_py]] — Historical backfill

## Data Flow

```
SAP HANA ──(read-only)──▶ SAPHanaConnector
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
            SAPSyncWorker           routes/orders.py
                    │                       │
                    ▼                       ▼
            OrderStatusManager ◀────── (updates)
                    │
                    ▼
            SQL Server (local) ◀── DatabaseClient
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   UserManager  RelacionMgr  AuditMgr
```

---
*Part of [[Home]] architecture*
