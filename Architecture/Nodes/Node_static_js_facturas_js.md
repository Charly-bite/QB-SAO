---
tags:
  - static
  - js
  - facturas
---
# 📜 static/js/facturas.js

> **Facturas tab JavaScript** — client-side logic for invoice management (~63KB).

## Role
Handles factura tab interactions: form submission, AJAX calls to factura API, dynamic table updates, daily order tracking, and extra item management.

## Used By
- [[Node_templates_orders_facturas_html]] — Standalone facturas page
- [[Node_templates_orders_partials__facturas_tab_html]] — Monitor facturas tab

## Communicates With
- [[Node_routes_orders_py]] — `/orders/api/facturas/*` endpoints
- [[Node_core_factura_metadata_manager_py]] — Backend data (via API)

## Part Of
- [[Frontend]]
