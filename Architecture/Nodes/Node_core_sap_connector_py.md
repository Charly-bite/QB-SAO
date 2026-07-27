---
tags:
  - core
  - py
  - database
  - sap
---
# 🔗 core/sap_connector.py

> Read-only connector to **SAP HANA** (SAP Business One ERP).

## Role
The largest core module (~53KB). Provides read-only access to SAP HANA for fetching order headers, order lines, customer data, invoices, and delivery notes. Manages connection pooling with auto-reconnect.

## Key Class: `SAPHanaConnector`
### Key Methods
- `connect()` / `disconnect()` — Connection management with retry
- `get_orders()` — Fetch order headers
- `get_order_lines(order_id)` — Fetch order line items
- `get_invoices()` — Fetch invoice data
- `get_deliveries()` — Fetch delivery notes
- `_ping_connection()` — Health check

## Depends On
- `hdbcli` (SAP HANA client library)
- `pandas` — Data manipulation
- Threading for connection management

## Used By
- [[Node_app_py]] — Initialized as `app.sap_connector`
- [[Node_routes_orders_py]] — On-demand SAP data refresh
- [[Node_core_sap_sync_worker_py]] — Background sync
- [[Node_scripts_backfill_auto_status_py]] — Historical data

## Part Of
- [[Core_Logic]], [[Database]]
