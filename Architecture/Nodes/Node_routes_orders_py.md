---
tags:
  - routes
  - py
  - orders
  - api
---
# 📦 routes/orders.py

> **The largest file in the project** (3700+ lines). Main orders blueprint handling all order UI and API endpoints.

## Role
Serves order list, monitor, facturas, detail, dashboard, visor, auditoria views. Provides JSON APIs for order status updates, SSE streaming, SGA webhooks, relaciones, facturas, and Excel export.

## UI Endpoints
| Route | Template |
|-------|----------|
| `/orders/` | [[Node_templates_orders_index_html]] |
| `/orders/monitor` | [[Node_templates_orders_monitor_html]] |
| `/orders/facturas` | [[Node_templates_orders_facturas_html]] |
| `/orders/<id>` | [[Node_templates_orders_detail_html]] |
| `/orders/dashboard` | [[Node_templates_orders_dashboard_html]] |
| `/orders/visor` | [[Node_templates_orders_visor_html]] |
| `/orders/auditoria` | [[Node_templates_orders_auditoria_html]] |
| `/orders/tiempos-tv` | [[Node_templates_orders_tiempos_tv_html]] |
| `/orders/changelog` | [[Node_templates_orders_changelog_html]] |

## API Endpoints
| Route | Method | Purpose |
|-------|--------|---------|
| `/orders/api/orders` | GET | Fetch orders (JSON) |
| `/orders/api/update-status` | POST | Update order status |
| `/orders/api/sga-label-printed` | POST | SGA webhook (CSRF-exempt) |
| `/orders/api/relaciones/*` | GET/POST | Shipping relations |
| `/orders/api/facturas/*` | GET/POST | Invoice metadata |
| `/orders/stream` | GET | SSE real-time events |
| `/orders/api/export-excel` | GET | Excel export |

## Key Features
- **SSE (Server-Sent Events)** for real-time monitor updates
- **Webhook retry queue** for missed SGA events
- **Weather cache** for TV monitor display
- **Excel export** via openpyxl

## Depends On
- [[Node_core_order_status_manager_py]] — `OrderStatus` enum, order operations
- [[Node_core_sap_connector_py]] — On-demand SAP data (via `current_app`)
- [[Node_core_user_manager_py]] — Role-based filtering (via `current_app`)
- [[Node_core_relacion_manager_py]] — Relaciones operations (via `current_app`)
- [[Node_core_factura_metadata_manager_py]] — Factura operations (via `current_app`)
- [[Node_core_audit_manager_py]] — Audit logging (via `current_app`)
- `openpyxl` — Excel export

## Used By
- [[Node_app_py]] — Registered as `orders_bp` blueprint
- [[Node_core_sap_sync_worker_py]] — References for sync context

## Part Of
- [[Routes]]
