---
tags:
  - core
  - py
  - database
---
# 🗃️ core/database_client.py

> SQL Server connection pool using pyodbc and SQLAlchemy.

## Role
The foundational data access layer. Provides a shared SQL Server connection pool with retry logic, used by all core managers for local data persistence.

## Key Class: `DatabaseClient`
- Connection string from `.env` (ODBC)
- Auto-reconnect with exponential backoff
- SQLAlchemy engine for advanced queries
- pyodbc for direct SQL execution

## Depends On
- `pyodbc` — ODBC driver
- `sqlalchemy` — Engine for connection pooling
- `dotenv` — Environment configuration

## Used By
- [[Node_core_order_status_manager_py]] — Order persistence
- [[Node_core_user_manager_py]] — User accounts
- [[Node_core_relacion_manager_py]] — Shipping relations
- [[Node_core_factura_metadata_manager_py]] — Invoice metadata
- [[Node_core_audit_manager_py]] — Audit logs
- [[Node_scripts_sync_print_jobs_job_py]] — Print job sync

## Part Of
- [[Core_Logic]], [[Database]]
