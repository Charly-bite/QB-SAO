---
tags:
  - core
  - py
  - business-logic
---
# 📦 core/relacion_manager.py

> Manages **Relación de Envíos** (shipping relation documents).

## Role
Handles creation, modification, and PDF generation of shipping relation documents. Links orders to their delivery relations and tracks signatures from facturación, crédito, and almacén departments.

## Key Class: `RelacionManager`

## Depends On
- [[Node_core_database_client_py]] — SQL Server persistence

## Used By
- [[Node_app_py]] — Instantiated as `app.relacion_mgr`
- [[Node_routes_orders_py]] — Relaciones API endpoints
- [[Node_templates_orders_partials__relaciones_tab_html]] — UI display
- [[Node_templates_orders_partials__relaciones_history_html]] — History view

## Part Of
- [[Core_Logic]]
