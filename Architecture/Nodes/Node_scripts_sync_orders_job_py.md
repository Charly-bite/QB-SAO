---
tags:
  - scripts
  - py
  - sync
---
# 🔄 scripts/sync_orders_job.py

> **Scheduled SAP → SQL order sync** — runs via Windows Task Scheduler.

## Role
Standalone script that creates a Flask app context, connects to SAP HANA, fetches new/updated orders, and pushes them into the local `OrderStatusManager`.

## Depends On
- [[Node_app_py]] — `create_app()` for Flask context
- [[Node_core_order_status_manager_py]] — `OrderStatus` enum, order updates

## Part Of
- [[Background_Jobs]], [[Scripts]]
