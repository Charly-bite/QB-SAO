---
tags:
  - core
  - py
  - sync
  - background
---
# 🔄 core/sap_sync_worker.py

> Background thread that periodically syncs data from SAP HANA.

## Role
A daemon thread started at application boot that continuously polls SAP HANA for new/updated orders and pushes changes into the local `OrderStatusManager`.

## Key Class: `SAPSyncWorker(threading.Thread)`
- Runs as a daemon thread (dies with the main process)
- Periodic sync interval
- Uses the Flask app context for database access

## Depends On
- [[Node_core_sap_connector_py]] — SAP HANA queries
- [[Node_core_order_status_manager_py]] — Order status updates (via app context)

## Used By
- [[Node_app_py]] — Started at boot: `app.sap_sync_worker = SAPSyncWorker(app)`

## Part Of
- [[Background_Jobs]], [[Core_Logic]]
