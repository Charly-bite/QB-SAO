---
tags:
  - scripts
  - py
  - sync
  - print
---
# 🖨️ scripts/sync_print_jobs_job.py

> **Print job sync from SGA** — matches SGA print events to orders.

## Role
Connects to the SGA database (SQL Server), reads print job records, uses `PrintEventMatcher` to find matching orders, and updates their status.

## Depends On
- [[Node_app_py]] — `create_app()` for Flask context
- [[Node_core_order_status_manager_py]] — `OrderStatus`, status updates
- [[Node_core_print_event_matcher_py]] — `extract_print_items`, `find_matching_order_ids`
- [[Node_core_database_client_py]] — SGA database connection

## Part Of
- [[Background_Jobs]], [[Scripts]]
