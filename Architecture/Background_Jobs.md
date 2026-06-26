# ⚙️ Background Jobs

> Asynchronous tasks that keep the system in sync with external data sources.

## Job Overview

| Job | File | Trigger | Purpose |
|-----|------|---------|---------|
| **SAP Sync Worker** | [[Node_core_sap_sync_worker_py]] | App startup (background thread) | Continuously syncs SAP HANA → local SQL |
| **Sync Orders Job** | [[Node_scripts_sync_orders_job_py]] | Windows Task Scheduler | Fetches new orders from SAP |
| **Sync Print Jobs** | [[Node_scripts_sync_print_jobs_job_py]] | Windows Task Scheduler | Syncs SGA print events to orders |
| **Print Daemon** | [[Node_scripts_sync_print_daemon_py]] | Windows service | Wraps sync_print_jobs_job in a daemon loop |
| **Backfill Status** | [[Node_scripts_backfill_auto_status_py]] | Manual / one-time | Backfills historical order statuses from SAP |
| **OpenOMS Sync Service** | [[Node_scripts_openoms_sync_service_py]] | Windows service | Service wrapper for sync processes |
| **Webhook Retry Worker** | [[Node_routes_orders_py]] | App startup (background thread) | Retries failed SGA label-printed webhooks |

## Data Flow

```
Windows Task Scheduler
        │
        ├── sync_orders_job.py ──▶ create_app() ──▶ SAP ──▶ OrderStatusMgr ──▶ SQL
        │
        └── sync_print_jobs_job.py ──▶ pyodbc ──▶ SGA DB ──▶ PrintEventMatcher ──▶ OrderStatusMgr

App Startup
        │
        ├── SAPSyncWorker (thread) ──▶ periodic SAP queries
        │
        └── Webhook Retry Worker (thread) ──▶ retries failed SGA webhooks
```

## Dependencies
- All sync jobs import from [[App_Factory]] (`create_app`)
- Use [[Node_core_order_status_manager_py]] for status updates
- Use [[Node_core_database_client_py]] for SQL Server access
- Use [[Node_core_print_event_matcher_py]] for matching print events

## Deployment
- Deploy scripts in `scripts/`: `deploy_dev.bat`, `deploy_prod.bat`
- Service management: `install_sync_service.bat`, `uninstall_sync_service.bat`
- See [[Node_scripts_openoms_sync_service_py]] and [[README_SYNC]]

---
*Part of [[Home]] architecture*
