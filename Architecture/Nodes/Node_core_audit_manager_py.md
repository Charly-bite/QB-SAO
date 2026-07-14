---
tags:
  - core
  - py
  - audit
---
# 📝 core/audit_manager.py

> Audit trail logging for all state changes.

## Role
Records all significant actions (status changes, user operations, login events) to create an auditable history.

## Key Class: `AuditManager`

## Depends On
- [[Node_core_database_client_py]] — SQL Server persistence

## Used By
- [[Node_app_py]] — Instantiated as `app.audit_mgr`
- [[Node_routes_orders_py]] — Logs status changes, user actions
- [[Node_templates_orders_auditoria_html]] — Audit log viewer

## Part Of
- [[Core_Logic]], [[Security]]
