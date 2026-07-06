---
tags:
  - core
  - py
  - business-logic
---
# 🧾 core/factura_metadata_manager.py

> Manages **invoice (factura) metadata** and daily order tracking.

## Role
Tracks which orders have been invoiced, manages daily order/extra metadata, and maintains the `factura_metadata.json`, `factura_daily_order.json`, and `factura_daily_extra.json` data files.

## Key Class: `FacturaMetadataManager`

## Depends On
- [[Node_core_database_client_py]] — SQL Server persistence

## Used By
- [[Node_app_py]] — Instantiated as `app.factura_metadata_mgr`
- [[Node_routes_orders_py]] — Factura API endpoints
- [[Node_templates_orders_facturas_html]] — Facturas page
- [[Node_templates_orders_partials__facturas_tab_html]] — Facturas tab
- [[Node_static_js_facturas_js]] — Client-side factura logic

## Part Of
- [[Core_Logic]]
